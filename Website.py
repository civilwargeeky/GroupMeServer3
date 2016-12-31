#Interface for handling web requests and serving files
import datetime
import http.cookies
import http.client
import json
import re
import os
from textwrap import dedent
from time import time
from urllib.parse import urlparse, parse_qs, urlencode
from uuid import uuid4

import Events
import Files
import Groups
import Logging as log
import MsgSearch
### CONFIG AREA ###
ID_LIFETIME = datetime.timedelta(days = 3).total_seconds() #We will tell to store cookie forever, but if its older than this we require a new sign-in
ID_FILE     = Files.getFileName("Server_UUIDs")
DEFAULT_DIR = "http"
ADMIN_PASSWORD = "shiboleeth" #I think that's the Canvas page for MST

NEVER_EXPIRES = "; expires=Fri, 31 Dec 9999 23:59:59 GMT" #Concatenate with cookies to make them never expire

### SECURITY MODULE ###
"""The security module handles keeping track of uuids sent to the website in a request of web resources"""
#The _idDict is a dict of uuid : tuple(last page access, [list of group IDs allowed in])
_idDict = None
#This goes through all uuids and checks their last time
def securityPurge():
  global _idDict
  if _idDict == None: securityLoad()
  timeNow = int(time())
  for user in _idDict.copy():
    if timeNow > _idDict[user][0] + ID_LIFETIME: #If the user has not logged for however long
      del _idDict[user] #Remove them from the list
  securitySave()

def securityLoad():
  global _idDict
  try:
    with open(ID_FILE, "r") as file:
      log.save("Loading ID file")
      _idDict = json.load(file)
    #Once file loaded, purge all non-existing IDs
    securityPurge()
  except (FileNotFoundError, json.decoder.JSONDecodeError):
    _idDict = {}
    log.save("ID file not found, using none")
  
def securitySave():
  log.save("Saving ID file")
  with open(ID_FILE, "w") as file:
    json.dump(_idDict, file)
    
def securityCanAccess(uuid, groupNum):
  if _idDict == None: securityLoad()
  if groupNum == None:
    return True #If doesn't belong to a group, always true
  if uuid == None:
    return False #Otherwise if has no idea, always false
    
  try:
    return groupNum in _idDict[uuid][1] #Return true if the user has this group saved, otherwise false
  except KeyError:
    return False #If the ID no longer exists, return false
    
#Makes a new UUID, adds it to the list of UUIDs, returns it
def securityRegister(uuid, groupNum):
  global _idDict
  if _idDict == None: securityLoad()
  try:
    _idDict[uuid][1].append(groupNum)
    _idDict[uuid][0] = int(time())
    return uuid
  except KeyError:
    uuid = str(uuid4())
    #Create a new entry
    _idDict[uuid] = [int(time()), [groupNum, ]]
    return uuid
  finally:
    securitySave()
    
### UTILITY FUNCTIONS ###

#POST: Returns the value of the cookie if it exists, else None
def getCookie(cookies, key):
  try:
    return cookies[key].value
  except (TypeError, KeyError): #TypeError if cookies is none
    return None
    
class Headers():
  def __init__(self):
    self._data = {}
    
  def addHeader(self, header, value):
    if not header in self._data:
      self._data[header] = [value,]
    else:
      self._data[header].append(value)
      
  #Like getitem, but always returns list
  def get(self, key):
    return self.__getitem__(key, alwaysList = True)
    
  #POST: If the key does not exist, raises KeyError. If the key has 1 value, returns the value. If more than 1, returns a list
  def __getitem__(self, key, alwaysList = False):
    if alwaysList or len(self._data[key]) > 1:
      return self._data[key][:] #Return a copy, no data editing
    return self._data[key][0] #If only one value, return the value
    
  #Modifies the first value with the given key. I.E. if there are two "Set-Header"s, it will only modify the first one
  def __setitem__(self, key, value):
    if key in self._data:
      self._data[key][0] = value
    else:
      self.addHeader(key, value)
      
  def __iter__(self): return self._data.__iter__()
  def __delitem__(self, key): del self._data[key]
  def __contains__(self, key): return key in self._data
  def __len__(self): return self._data.__len__()
    
    
#PRE: Takes a mapping or Headers object
#POST: If any values, returns "?" followed by the values encoded as url parameters. Otherwise ""
def addParams(obj):
  if len(obj) == 0:
    return ""
  if type(obj) == Headers:
    tempObj = []
    for key in obj:
      for val in obj[key]:
        tempObj.append((key,val))
    return "?"+urlencode(tempObj)
  return "?"+urlencode(obj)
    
### REQUEST HANDLING ###

#Intended to be used as a decorator for do_... functions. Describes the extensions this method is valid for
#NOTE: By default, "html" will be used for a function
#Example:
#  @extSupport("html","css","js")
#  def do_dataPage(self, num): ...
#
#  would register that this function should receive messages for "dataPage.html" as well as "dataPage.js"
def extSupport(*arg):
  def addExt(function): 
    function._supportedExtensions = list(arg)
    return function
  return addExt

def handleRequest(method, handler):
  if method == "POST":
    #log.net.debug("Handling POST")
    return PostHandler(handler).handle()
  elif method == "GET":
    #log.net.debug("Handling GET")
    return GetHandler(handler).handle()
  else:
    log.net.error("Cannot handle request of type", method)
    
#This is just the generic handler. Should use POST or GET handler for specific requests
#A handler is instantiated for a single request
class Handler:
  CHUNK_SIZE   = 1024 * 256 #The size of a buffer chunk to download/upload at once. 1/4 MB
  PAGE_NO_PATH = "/noFile.html"
  PAGE_DEFAULT = "/selectionScreen.html" #Default webpage to send to
  PAGE_ICON    = "/favicon.ico"
  PAGE_INDEX   = "index.html" #Default per-group page
  PAGE_DEF_GEN = "default.html" #Default file to be generated from
  ENCODING     = "utf-8"     #Encoding to use when sending text data
  STR_CONTENT  = "%content%" #String to replace for content
  STR_TITLE    = "%title%"   #String to replace for page title
  COOKIE_ID    = "user_id" #The cookie key for user id
  ERR_NO_GRP   = "No group associated with web request"
  requestsProcessed = 0 #Reset every time server starts
  
  #A generated file will have two strings in it, a "%title%" and a "%content%" so that the page can be properly generated
  #The genFiles will be a list of "requestFile"
  genFiles = None #List of files that should be generated on request (rather than served)

  def __init__(self, handler):
    self.handler = handler
    self.url     = urlparse(handler.path)
    self.params  = parse_qs(self.url.query) or {}
    #log.debug("Path:  ", handler.path)
    #log.debug("URL:   ", self.url)
    #log.debug("Params:",self.params)
    #List of request headers
    self.headers = handler.headers
    #The local file path to get files from
    self.fileName = os.path.normpath(self.url.path).strip(os.sep) #Strip these slashes from both sides or else things mess up when loading files
    #Organize the cookies (if we have any)
    self.cookies = http.cookies.BaseCookie(self.handler.headers['cookie']) if ('cookie' in self.handler.headers) else None
    self.group = None #The group number
    self.groupObj = None #The group object
    self.responseSent = False #After we call "sendResponse" then we can't send headers again
    
    #We won't actually send data until we are sure that we have it all
    self.buffer = "".encode(self.ENCODING)
    
    #Checking for a group folder
    try:
      splitPath = os.path.split(self.fileName) #splits into (everything besides tail, tail)
      #NOTE: A really nice thing about this is that all hyperlinks are paths relative to a folder unless otherwise specified :D
      #NOTE ON IMPLEMENTATION: this naiive assumption is that we will never be in a folder besides base or a group number
      self.group = int(splitPath[0]) #I expect the most folder complexity to be "group/file"
      self.groupObj = Groups.getGroup(self.group)
      self.fileName = splitPath[1] #If we have a group, modify the fileName to not contain the group
    except ValueError: #Not part of a group
      pass
    
    if self.genFiles == None: #If the list of files isn't loaded
      self.loadGenFiles()
    
    #log.debug("Group: ", self.group)
    log.web.low("New Handler for Url: ", self.url)
  
  #This will actually get the list of file we can process from the methods that exist
  #Note: This will be used by subclasses. So a GET handler will register all the GET pages we can use
  @classmethod
  def loadGenFiles(cls):
    log.web("Loading generated files for",cls.__name__)
    cls.genFiles = []
    for method in dir(cls): #We just go through all the methods available in the class
      if method.startswith("do_"):
        function = getattr(cls, method)
        if hasattr(function, "_supportedExtensions"):
          extList = function._supportedExtensions
        else:
          extList = ["html",]
        for ext in extList: #Adds all the pages to look out for
          #These should look like "do_page" --> "page.html"
          #The "if ext else"... because we can have no extension as well
          cls.genFiles.append(method.replace("do_","",1)+("." if ext else "")+ext)
    log.web("Files available:", cls.genFiles)
  
  def existsFile(self, path):
    return os.path.exists(path) and os.path.isfile(path)
    
  #Handle takes an arbitrary request (GET or POST) and processes it, sending back data if necessary
  def handle(self):
    Handler.requestsProcessed += 1
    log.net("(#{}) File Requested: '{}'".format(Handler.requestsProcessed, self.fileName) + \
      (" for group {}".format(self.group) if self.group else ""))
      
    #Checking for user authorization
    self.userID = getCookie(self.cookies, self.COOKIE_ID)
    if not securityCanAccess(self.userID, self.group) and not self.fileName.endswith("password.html"):
      log.security("User not allowed to access", self.fileName+", returning password page")
      return self.redirectFile("password.html"+addParams({"redirect":self.fileName})) #Redirect back to the requested page when done
    
    try:
      return self.sendFile(self.fileName)
    except Exception as e: #Not BaseException though
      #In the event of any error, set this
      self.sendError(str(e))
      raise e #Raise it again so I can see what's going on
      
    
  def loadFile(self, path, shouldError = True): #Simple file loading mechanism
    path = path.strip(os.sep)
    try:
      with open(path) as file:
        return file.read()
    except FileNotFoundError:
      if not DEFAULT_DIR in os.path.split(path)[0]: #Also try to load from the DEFAULT_DIR, because most documents will be there
        return self.loadFile(os.path.join(DEFAULT_DIR, path))
      if shouldError: #If we should raise the error, re-raise the error
        raise FileNotFoundError("Could not load file: " + path)
      return False
    
  #This does the actual loading and sending of files
  def yieldFile(self, path):
    path = path.strip(os.sep)
    with open(path, "rb") as handle:
      #yield handle.read() #Super simple way
      while True:
        data = handle.read(self.CHUNK_SIZE) #Don't load too much data at once.
        if not data: break #Check if any more data to read
        yield data #Return this bit of data
        
  def writeText(self, text):
    self.buffer += text.encode(self.ENCODING)
    
  #Just sends headers and code
  #PRE: Use sendData = False if some other part of the method can add to the buffer, 
  #       and the buffer should not be sent (like for errors and such)
  #POST: Returns true if new response is sent. False if response has already been sent
  def sendResponse(self, code = http.client.OK, headers = None, sendData = True):
    if self.responseSent:
      return False
    self.handler.send_response(code)
    if headers != None:
      for key in headers:
        toSend = headers[key] #Get values
        if type(toSend) != list: #If there was only 1
          toSend = [headers[key],]
          
        for val in toSend: #Then send all repetitions for this value
          self.handler.send_header(key, val)
    self.handler.end_headers()
    self.responseSent = True
    if sendData:
      self.sendData()
    return True
        
  def sendData(self):
    while len(self.buffer) > 0:
      self.handler.wfile.write(self.buffer[:self.CHUNK_SIZE])
      self.buffer = self.buffer[self.CHUNK_SIZE:]
      
  def sendError(self, errorMsg = "[No message]"):
    self.buffer = ("Error: " + errorMsg + "\n").encode(self.ENCODING)
    self.sendResponse(http.client.INTERNAL_SERVER_ERROR)
    
  #This will actually do the sending of the response over a handler
  #PRE: path is the path requested (not including the group directory element)
  #     code is the numeric response code to send
  #     headers is a dict of any additional headers we need to send
  #headers is response headers to send along with the request, NOT THE HEADERS WE GOT
  def sendFile(self, path, code = http.client.OK, headers = None):
    if headers == None: headers = Headers()
    if not path: #If the path is blank
      return self.redirectFile(self.PAGE_DEFAULT, headers = headers)
      
    path = path.strip("/") #Because I use / for absoulte and it messes up file serving
    
    #Checking for generated files
    if path in self.genFiles:
      try:
        method = getattr(self, "do_"+path.split(".")[0]) #Get the path before .html
      except AttributeError:
        log.web.error("No Generation Function for path",path) #Otherwise just return the basic file and log error
      else: #Don't want to catch errors from these
        return method() #Call the function
    
    #log.debug("File requested for path: '"+path+"'")
    if not self.existsFile(path):
      path = os.path.join(DEFAULT_DIR, path)
      if not self.existsFile(path) and not path.endswith(self.PAGE_NO_PATH): #We will always be able to access PAGE_NO_PATH, but don't create an infinite loop
        log.net.error("Cannot find file for path '"+path+"', returning",self.PAGE_NO_PATH)
        #return self.redirectFile(self.PAGE_NO_PATH)
        return self.sendFile(self.PAGE_NO_PATH, code = http.client.NOT_FOUND, headers = headers)
        
    #The page exists
    self.sendResponse(code, headers, sendData = False)
    for data in self.yieldFile(path):
      self.handler.wfile.write(data) #Incrementally writes data back to web
        
  def redirectFile(self, path, headers = None):
    if headers == None:
      headers = Headers()
    headers["Location"] = path
    return self.sendResponse(http.client.FOUND, headers, sendData = False)
    
class PostHandler(Handler):

  #Note: If they are redirected from handle (not having access), they should have a "redirect" parameter
  #This will always return 200, but the value of the response determines what happens
  def do_password(self):
    groupNum = self.group
    log.web.debug("Processing Password")
    queries = parse_qs(self.handler.body)
    try:
      password = queries["pass"][0]
      log.website.debug("Password sent:",password)
      if password == ADMIN_PASSWORD: #Possibly set the admin password
        log.web.debug("New admin admitted")
        self.writeText("Admin Access Granted!")
        self.sendResponse(headers = {"Set-Cookie":"administrator=true"+NEVER_EXPIRES})
      elif password == Groups.getGroup(groupNum).getPassword():
        log.web.debug("User entered correct password for group",groupNum)
        id = securityRegister(self.userID, groupNum)
        #This is the next site to visit, and is stored as a header in "Location"
        nextPage = self.params['redirect'][0] if 'redirect' in self.params else self.PAGE_INDEX
        #Sends 200 even though its a redirect because AJAX will just follow redirects. Not what I want
        self.sendResponse(headers = {"Set-Cookie":self.COOKIE_ID+"="+id+NEVER_EXPIRES, "Location":nextPage})
      else:
        log.web.debug("Password incorrect")
        self.writeText("Password Incorrect!")
        self.sendResponse()
    except (KeyError, IndexError): #Catch if no password part or no [0] term
      log.web.error("No Password Sent")
      self.sendError("No Password Sent!")

  
class GetHandler(Handler):
  def do_addresses(self):
    log.web.debug("Sending Addresses Screen")
    toSend = self.loadFile(self.PAGE_DEF_GEN)
    group = self.groupObj
    if group:
      toWrite = '<table border="1" width="100%">'
      for user in group.users.getUsersSorted(lambda user: user.getName()):
        name = user.getName()
        #Add in their home address (or a default)
        addressesRaw = [("Home", user.getAddress() or "No Home Address")]
        #Add in all other addresses (if they have one. If not, getAddress returns false)
        addressesRaw.extend([(type, user.getAddress(type)) for type in Events.ADDRESS_MODIFIERS if user.getAddress(type)])
        maxLength = str(max(len("Home"), len(max(Events.ADDRESS_MODIFIERS, key = len)))) #Gets the length of the longest string (as a string) from address modifiers
          #This part is just the html for where to insert the address and name
        toWrite += '<tr><td class="AddressLeft">{}</td><td>{}</td></tr>'.format(user.getName(), \
                   "<br>".join([("{:"+maxLength+"}: {}").format(data[0].title(), data[1]) for data in addressesRaw])) #This goes through each address, and adds the type (justified to max length), and then the address
      toWrite += "</table>" #End HTML tag
    else:
      toWrite = "No group associated??? (Yell at Daniel)"
      
    toSend = toSend.replace(self.STR_TITLE  , "Addresses")
    toSend = toSend.replace(self.STR_CONTENT, toWrite)
    
    self.writeText(toSend)
    self.sendResponse()
    
  @extSupport("")
  def do_getLog(self):
    fileName = Files.getLog()
    log.web.debug("Redirecting to log file:",fileName)
    self.redirectFile("/"+fileName)
  
  def do_searchResults(self):
    log.web.debug("Starting search results")
    toSend = self.loadFile(self.PAGE_DEF_GEN)
    group = self.groupObj
    if group:
      numFound = 0
      maxResults = 250
      numAround  = 2 #Number on either side of found
      nameLimit = 20 #Characters for a group name
      #We are going to be yielding data so we do not need to buffer
      
      if 'query' in self.params:
      
        query = self.params["query"][0]
        permissiveSearch = "strict" in self.params and (self.params["strict"][0] == "false")
        log.web("Starting search results for query: ",query)
        
        #This will be copied and modified by every search result
        mainMessage = """<tr class="SearchContainer {subclass}" id="{resultNum}{position}">
          <td class="SearchLeft"><div style="text-align:center;padding=0px;margin=px">{userName}</div>{groupName}<br>{date}</td>
          <td class="SearchPicture"><img class = "SearchPicture" src="{avatar}"></td>
          <td class="SearchRight"><div class="SearchResults">
            {text}
            </div></td>
        </tr>\n"""

        #Send top part of html
        self.writeText(toSend.split(self.STR_CONTENT)[0].replace(self.STR_TITLE, "Search Results"))
        
        #Write initial scripts
        self.writeText('''<script src="util.js"></script>
                          <script src="searchClickScript.js"></script>
                          <form action="search.html"><button style="display:inline-block;width:100%;">Do another search!</button></form>
                          <p>Your Search: {query}</p><br>
                          <table border="5" width="100%" sytle="table-layout:fixed">'''.format(query = query))
        i=-1
        searcher = MsgSearch.getSearcher(group)
        for message in searcher:
          i += 1
          #Iterates through all words of prompt if permissive, otherwise through a tuple containing only the query
          for word in (re.split("\W+", query) if permissiveSearch else (query,)):
            #Searches for the word(s) in each message (text can be None)
            if message.text and re.search(word, message.text, re.IGNORECASE):
              #And the message and surrounding ones
              #This directly sends each search result as its generated
              lowerBound = max(i-numAround, 0)
              upperBound = min(i+numAround+1, len(searcher)-1)
              index = lowerBound #Index starts at this bound, and increases to upperBound-1
              for message in searcher[lowerBound : upperBound]:
              
                #Get user's name (or system) for display
                userName = message.getUserString()
                if message.isUser():
                  user = group.users.getUserFromID(message.user_id)
                  if user:
                    userName = user.getName()
                    
                #Just directly writes this part as soon as its done
                self.writeText(mainMessage.format(\
                  #Only the main result should be visible
                  subclass = ("" if index == i else "Hidden"), \
                  #The result number on the page
                  resultNum = str(numFound), \
                  #If not the initial value, sets the index to the difference in index and lower bound, then subtracts another if it is after the intitial value
                  position = ("" if index == i else (" "+str(index-lowerBound-int(index >= i)))), \
                  #User's name or "calendar" or "system" or whatever
                  userName  = userName, 
                  #The group's name (shortened)
                  groupName = (group.getName()[:nameLimit] + ("..." if len(group.getName()) >= nameLimit else "")), 
                  #Add date message was sent
                  date = datetime.date.fromtimestamp(int(message["created_at"])).strftime("%m/%d/%y"), \
                  #The user's avatar url (if none it will put the icon of it)
                  avatar = (message["avatar_url"] or self.PAGE_ICON), \
                  #The actual message text
                  text = (message["text"] or "").replace("\n","<br>"))\
                  )
                index += 1 #Increment index
              
              numFound += 1 #Add that we have found another matched
              break #Don't want to generate multiple results from the same message
          if numFound > maxResults: #So people don't break the server
            break
        
        self.writeText("</table>")
        if numFound == 0:
          self.writeText("No messages matched your search")
        if numFound > maxResults:
          self.writeText("Too Many Results...")
          
        #Send bottom part of html
        self.writeText(toSend.split(self.STR_CONTENT, 1)[1]) #Split with max split size of 1
        
        self.sendResponse() #Then send all the data
      else:
        self.sendError("No query found in search!")
        raise RuntimeError("No query in search") #Gets picked up to send error
  
  def do_selectionScreen(self):
    log.web.debug("Sending Selection Screen")
    basicFile = self.loadFile(self.fileName)
    
    content = ""
    for group in Groups.getSortedList(groupType = Groups.MainGroup): #Get a list of all the main groups
      if group.getID() != 99: #If is not error group
        content += dedent("""\
        <tr onclick="document.location = '{group}/index.html'">
          <td valign="middle" style="text-align:center"><p style="font-size:110%;margin:5pt">{groupName}</p><p style="font-size:100%;font-style:italic;color:#008800;margin:5pt">Group {group}</p></td>
          <td width = 1pt><img src="{groupImage}" style="vertical-align:middle;width:90px"></td>
        </tr>""".format(group = group.getID(), groupName = group.getName(), groupImage = group.image or self.PAGE_ICON))
      
    basicFile = basicFile.replace(self.STR_CONTENT, content)
    
    self.writeText(basicFile)
    self.sendResponse() #Send good response
    
  @extSupport("")
  def do_shutdownserver(self):
    if getCookie(self.cookies, "administrator"): #Here be admin access
      Events.NonBlockingShutdownLock.acquire(blocking = False)
      log.info("SHUTTING DOWN SERVER!!! (from web request)")
      return self.redirectFile(self.PAGE_DEFAULT)
    else:
      return self.sendFile("noAuth.html", http.client.FORBIDDEN)
          
  @extSupport("")
  def do_restartserver(self):
    if getCookie(self.cookies, "administrator"): #Here be admin access
      Events.NonBlockingRestartLock.acquire(blocking = False)
      log.info("Restarting Server (from web request)!")
      return self.redirectFile(self.PAGE_DEFAULT)
    else:
      return self.sendFile("noAuth.html", http.client.FORBIDDEN)
    
  def do_users(self):
    group = self.groupObj
    if not group:
      return self.sendError(self.ERR_NO_GRP)
    file = self.loadFile(self.fileName)
    names = "<option value=''>[None]</option>\n"
    #Note: True is for "preferGroupMe"
    nextUser = lambda user: "<option value='{}'>{}</option>\n".format(user.ID, user.getName(True))
    for user in group.users.getUsersSorted(lambda user: user.getName(True)):
      names += nextUser(user)
    file = file.replace(self.STR_CONTENT, names, 1)
    
    self.writeText(file)
    self.sendResponse()
  
  #This should be called from the users page only
  #in mode 'get' will return html for viewing the users names
  #in mode 'set' will set a name as the user's real name
  #in mode 'remove' will remove the given name
  #in mode 'add' will add the given name
  #PARAM: type - the mode this function operates in
  #       user - the id of the requested user
  #       name - the name to do a function with (only in 'set' and 'remove')
  #POST: in modes besides 'get' will send "success" if the name existed already and "failure" if it did not
  @extSupport("") #Supports only empty extension
  def do_userRequest(self):
    group = self.groupObj
    if not group:
      return self.sendError(self.ERR_NO_GRP)
      
    try:
      mode = self.params['type'][0]
      userID = self.params['user'][0] #Each key of params is a list
      user = group.users.getUserFromID(userID)
      log.web.debug("Found user from", userID,":",user)
      if not user: raise KeyError
    except KeyError:
      return self.sendError("No user found/sent or improper parameters")
      
    name = self.params.get('name', (None,))[0] #Gets the name if it exists (default None)
    
    toSend = ""
    if mode == "get":
      log.web.debug("Mode: Get")
      toSend+= "Note: <b>R</b> is for 'Real Name' and <b>D</b> is for 'Delete Name'<br>The box at the top is for adding new names<br><br>"
      toSend+= "Data for user: <b>{}</b>\n".format(user.getName(preferGroupMe = True))
      toSend+= dedent("""\
        <table border=1>
          <tr>
            <td colspan="3"><center>User's Names</center></td>
          </tr>
          <tr>
            <td><center><input style="width:95%" type="text" id="nameSubmit"></center></td>
            <td colspan="2"><center><input onclick="newName()" type="submit" value="New!"></center></td>
          </tr>
      """)
      for name in sorted(user.alias):
        toSend+= "<tr>\n"
        toSend+= "  <td><span style='margin:10px'>{}</span></td>\n".format(user.specifyName(name))
        if name != user.realName:
          toSend+= "  <td><input type='submit' onclick='{}' value='R' title='Make this name the real name'></td>\n"\
          .format("setName(\""+name.replace("'","\'").replace("\"","\\\"")+"\")")
        else:
          toSend+= "  <td></td>\n" # If this is the real name, don't include it
        if name != user.GMName:
          toSend+= "  <td><input type='submit' onclick='{}' value='D' title='Delete this name for this user'></td>\n"\
          .format("removeName(\""+name.replace("'","\'").replace("\"","\\\"")+"\")")
        else:
          toSend+= "  <td></td>\n" #Cannot remove groupMe name
        toSend+= "</tr>\n"
      toSend+= "</table>"
    else:  
      if mode == "set": #We are setting a name as real name
        log.web.debug("Mode: Set real name to", name)
        toSend+= "success" if (user.hasName(name) and user.addName(name, realName = True)) else "failure"
          
      elif mode == "remove": #We are removing the given name
        log.web.debug("Mode: Removing name -",name)
        toSend+= "success" if (user.hasName(name) and user.removeName(name)) else "failure"
        
      elif mode == "add": #We are adding a new name
        log.web.debug("Mode: Adding name",name)
        toSend+= "success" if user.addAlias(name) else "failure"
       
      group.save()
    
    self.writeText(toSend)
    self.sendResponse()