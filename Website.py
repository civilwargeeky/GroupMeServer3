#Interface for handling web requests and serving files
import datetime
import http.cookies
import http.client
import json
import re
import os
from time import time
from urllib.parse import urlparse, parse_qs
from uuid import uuid4

import Events
import Files
import Groups
import Logging as log
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
    
    
### REQUEST HANDLING ###

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
class Handler:
  PAGE_NO_PATH = "/noFile.html"
  PAGE_DEFAULT = "/selectionScreen.html" #Default webpage to send to
  PAGE_ICON    = "/favicon.ico"
  PAGE_INDEX   = "index.html" #Default per-group page
  PAGE_DEF_GEN = "default.html" #Default file to be generated from
  ENCODING     = "utf-8"     #Encoding to use when sending text data
  STR_CONTENT  = "%content%" #String to replace for content
  STR_TITLE    = "%title%"   #String to replace for page title
  COOKIE_ID    = "user_id" #The cookie key for user id
  requestsProcessed = 0 #Reset every time server starts
  
  #A generated file will have two strings in it, a "%title%" and a "%content%" so that the page can be properly generated
  #The genFiles will be a list of "requestFile"
  genFiles = None #List of files that should be generated on request (rather than served)

  def __init__(self, handler):
    self.handler = handler
    self.url     = urlparse(handler.path)
    #List of request headers
    self.headers = handler.headers
    #The local file path to get files from
    self.fileName = os.path.normpath(self.url.path).strip(os.sep) #Strip these slashes from both sides or else things mess up when loading files
    #Organize the cookies (if we have any)
    self.cookies = http.cookies.BaseCookie(self.handler.headers['cookie']) if ('cookie' in self.handler.headers) else None
    groupNum = re.search("\AGroup (\d+)", self.url.path.lstrip("/"))
    self.group = Groups.getGroup(int(groupNum.group(1))) if groupNum else None
    
    if self.genFiles == None: #If the list of files isn't loaded
      self.loadGenFiles()
    
    #log.debug("Group: ", self.group)
    log.web.low("New Handler for Url: ", self.url)
  
  @classmethod
  def loadGenFiles(cls):
    try:
      with open(cls.GEN_PATH) as file:
        cls.genFiles = json.load(file)
        log.web("Successfully loaded GEN_PATH files!")
        log.debug(cls.genFiles)
    except FileNotFoundError:
      log.web.error("Could not find GEN_PATH file!")
      raise FileNotFoundError("Could not find {} file!".format(cls.GEN_PATH)) from None #Also should be breaking
    except ValueError:
      log.web.error("JSON could not parse GEN_PATH file! (file empty?)")
      raise ValueError("JSON parse fail for loading GEN_PATH") from None #This should be breaking
  
  def existsFile(self, path):
    return os.path.exists(path) and os.path.isfile(path)
    
  #Handle takes an arbitrary request (GET or POST) and processes it, sending back data if necessary
  def handle(self):
    Handler.requestsProcessed += 1
    log.net("File Requested: '{}' (#{})".format(self.fileName, Handler.requestsProcessed))
    
    #Checking for a group folder
    try:
      splitPath = os.path.split(self.fileName)
      #NOTE: A really nice thing about this is that all hyperlinks are paths relative to a folder unless otherwise specified :D
      group = int(splitPath[0]) #I expect the most folder complexity to be "group/file"
      self.fileName = splitPath[1] #If we have a group, modify the fileName to not contain the group
    except ValueError: #Not part of a group
      group = None
      
    #Checking for user authorization
    self.userID = getCookie(self.cookies, self.COOKIE_ID)
    if not securityCanAccess(self.userID, group) and not self.fileName.endswith("password.html"):
      log.security("User not allowed to access", self.fileName+", returning password page")
      return self.redirectFile(group, "password.html")
    
    return self.sendFile(group, self.fileName)
    
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
        data = handle.read(1024 * 256) #Don't load too much data at once.
        if not data: break #Check if any more data to read
        yield data #Return this bit of data
        
  def writeText(self, text):
    return self.handler.wfile.write(text.encode(self.ENCODING))
    
  #Just sends headers and code
  def sendResponse(self, code = http.client.OK, headers = {}):
    self.handler.send_response(code)
    for key in headers:
      self.handler.send_header(key, headers[key])
    self.handler.end_headers()
    
  #This will actually do the sending of the response over a handler
  #headers is response headers to send along with the request, NOT THE HEADERS WE GOT
  def sendFile(self, group, path, code = http.client.OK, headers = {}):
    if not path: #If the path is blank
      return self.redirectFile(group, self.PAGE_DEFAULT, headers = headers)
      
    path = path.strip("/") #Because I use / for absoulte and it messes up file serving
    
    isAdmin = getCookie(self.cookies, "administrator")
    if path in ["restartserver","shutdownserver"]:
      if isAdmin: #Here be admin access
        if path == "restartserver":
          Events.NonBlockingRestartLock.acquire(blocking = False)
          log.info("Restarting Server (from web request)!")
        if path == "shutdownserver":
          Events.NonBlockingShutdownLock.acquire(blocking = False)
          log.info("SHUTTING DOWN SERVER!!! (from web request)")
        return self.redirectPage(group, self.PAGE_INDEX)
      else:
        return self.sendFile(group, "noAuth.html", http.client.FORBIDDEN)
    
    #Checking for generated files
    if path in self.genFiles:
      try:
        method = getattr(self, "do_"+path.split(".")[0]) #Get the path before .html
      except AttributeError:
        log.web.error("No Generation Function for path",path) #Otherwise just return the basic file and log error
      else: #Don't want to catch errors from these
        return method(group) #Call the function, passing in what group to call
    
    #log.debug("File requested for path: '"+path+"'")
    if not self.existsFile(path):
      path = os.path.join(DEFAULT_DIR, path)
      if not self.existsFile(path) and not path.endswith(self.PAGE_NO_PATH): #We will always be able to access PAGE_NO_PATH, but don't create an infinite loop
        log.net.error("Cannot find file for path '"+path+"', returning",self.PAGE_NO_PATH)
        #return self.redirectFile(group, self.PAGE_NO_PATH)
        return self.sendFile(group, self.PAGE_NO_PATH, code = http.client.NOT_FOUND, headers = headers)
        
    #The page exists
    self.sendResponse(code, headers)
    for data in self.yieldFile(path):
      self.handler.wfile.write(data) #Incrementally writes data back to web
        
  def redirectFile(self, group, path, headers = None):
    if not headers:
      headers = {}
    headers["Location"] = path
    return self.sendFile(group, self.PAGE_NO_PATH, code = http.client.FOUND, headers = headers)
    
class PostHandler(Handler):
  GEN_PATH     = Files.getFileName("GEN_POST_FILES", prefix = "")
  
  def do_password(self, groupNum):
    log.web.debug("Processing Password")
    queries = parse_qs(self.handler.body)
    try:
      password = queries["pass"][0]
      log.website.debug("Password sent:",password)
      if password == ADMIN_PASSWORD: #Possibly set the admin password
        log.web.debug("New admin admitted")
        self.redirectFile(groupNum, self.PAGE_INDEX, {"Set-Cookie":"administrator=true"+NEVER_EXPIRES})
      elif password == Groups.getGroup(groupNum).getPassword():
        log.web.debug("User entered correct password for group",groupNum)
        id = securityRegister(self.userID, groupNum)
        self.redirectFile(groupNum, self.PAGE_INDEX, {"Set-Cookie":self.COOKIE_ID+"="+id+NEVER_EXPIRES})
      else:
        self.sendFile(groupNum, "password.html") #Just send them back to same page
    except (KeyError, IndexError): #Catch if no password part or no [0] term
      log.web.error("No Password Sent")
      self.sendResponse(http.client.INTERNAL_SERVER_ERROR)

  
class GetHandler(Handler):
  GEN_PATH     = Files.getFileName("GEN_GET_FILES", prefix = "")

  def do_addresses(self, group):
    log.web.debug("Sending Addresses Screen")
    toSend = self.loadFile(self.PAGE_DEF_GEN)
    group = Groups.getGroup(group)
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
                   "<br>".join([("{:"+maxLength+"}: {}").format(data[0], data[1]) for data in addressesRaw])) #This goes through each address, and adds the type (justified to max length), and then the address
      toWrite += "</table>" #End HTML tag
    else:
      toWrite = "No group associated??? (Yell at Daniel)"
      
    toSend = toSend.replace(self.STR_TITLE  , "Addresses")
    toSend = toSend.replace(self.STR_CONTENT, toWrite)
    
    self.sendResponse()
    self.writeText(toSend)
    
  
  def do_selectionScreen(self, _): #We don't care for group
    log.web.debug("Sending Selection Screen")
    basicFile = self.loadFile(self.fileName)
    
    content = ""
    for group in Groups.getSortedList(groupType = Groups.MainGroup): #Get a list of all the main groups
      if group.getID() != 99: #If is not error group
        content += \
        """<tr onclick="document.location = '{group}/index.html'">
          <td valign="middle" style="text-align:center"><p style="font-size:110%;margin:5pt">{groupName}</p><p style="font-size:100%;font-style:italic;color:#008800;margin:5pt">Group {group}</p></td>
          <td width = 1pt><img src="{groupImage}" style="vertical-align:middle;width:90px"></td>
        </tr>""".format(group = group.getID(), groupName = group.getName(), groupImage = group.image or self.PAGE_ICON)
      
    basicFile = basicFile.replace(self.STR_CONTENT, content)
    
    self.sendResponse() #Send good response
    self.writeText(basicFile)