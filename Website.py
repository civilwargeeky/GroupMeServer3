#Interface for handling web requests and serving files
import datetime
import http.client
import json
import re
import os
from urllib.parse import urlparse

import Files
import Groups
import Logging as log
### CONFIG AREA ###
ID_LIFETIME = datetime.timedelta(days = 3)
ID_FILE     = Files.getFileName("Server_IDs")
DEFAULT_DIR = "http"

### SECURITY MODULE ###
"""The security module handles keeping track of uuids sent to the website in a request of web resources"""
_idDict = {}
def securityLoad():
  global _idDict
  try:
    with Files.SafeOpen(ID_FILE, "r") as file:
      log.save("Loading ID file")
      _idDict = json.load(file)
  except (FileNotFoundError, json.decoder.JSONDecodeError):
    log.save("ID file not found, using none")
  
def securitySave():
  log.save("Saving ID file")
  with Files.SafeOpen(ID_FILE, "w") as file:
    json.dump(_idDict, file)
    
    
    
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
  NO_PATH      = "noFile.html"
  DEFAULT_PATH = "selectionScreen.html"
  GEN_PATH     = Files.getFileName("GEN_FILES", prefix = "")
  ENCODING     = "utf-8"
  STR_CONTENT  = "%content%"
  STR_TITLE    = "%title%"
  requestsProcessed = 0 #Reset every time server starts
  
  #A generated file will have two strings in it, a "%title%" and a "%content%" so that the page can be properly generated
  #The genFiles will be a dict of "requestFile":"fileToLoad" so "searchResults.html":"default.html"
  genFiles = None #List of files that should be generated on request (rather than served)

  def __init__(self, handler):
    self.handler = handler
    self.url     = urlparse(handler.path)
    self.headers = handler.headers
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
    self.fileName = os.path.normpath(self.url.path).strip(os.sep) #Strip these slashes from both sides or else things mess up when loading files
    Handler.requestsProcessed += 1
    log.net("File Requested: '{}' (#{})".format(self.fileName, Handler.requestsProcessed))
    
    try:
      splitPath = os.path.split(self.fileName)
      log.debug("Split path:",splitPath)
      #NOTE: A really nice thing about this is that all hyperlinks are paths relative to a folder unless otherwise specified :D
      group = int(splitPath[0]) #I expect the most folder complexity to be "group/file"
      self.fileName = splitPath[1] #If we have a group, modify the fileName to not contain the group
    except ValueError: #Not part of a group
      group = None
      
    if self.fileName in self.genFiles:
      try:
        method = getattr(self, "do_"+self.fileName.split(".")[0]) #Get the fileName before .html
        return method(group) #Call the function, passing in what group to call
      except AttributeError:
        log.web.error("No Generation Function for path",self.fileName) #Otherwise just return the basic file and log error
    
    return self.sendFile(group, self.fileName)
    
  def loadFile(self, path): #Simple file loading mechanism
    try:
      with open(path) as file:
        return file.read()
    except FileNotFoundError:
      if not DEFAULT_DIR in os.path.split(path)[0]: #Also try to load from the DEFAULT_DIR, because most documents will be there
        return self.loadFile(os.path.join(DEFAULT_DIR, path))
      return False
    
  #This does the actual loading and sending of files
  def yieldFile(self, path):
    with open(path, "rb") as handle:
      #yield handle.read() #Super simple way
      while True:
        data = handle.read(1024 * 256) #Don't load too much data at once.
        if not data: break #Check if any more data to read
        yield data #Return this bit of data
    
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
      return self.redirectFile(group, self.DEFAULT_PATH, headers = headers)
      
    #log.debug("File requested for path: '"+path+"'")
    if not self.existsFile(path):
      
      path = os.path.join(DEFAULT_DIR, path)
      if not self.existsFile(path) and not path.endswith(self.NO_PATH): #We will always be able to access NO_PATH, but don't create an infinite loop
        log.net.error("Cannot find file for path '"+path+"', returning",self.NO_PATH)
        #return self.redirectFile(group, self.NO_PATH)
        return self.sendFile(group, self.NO_PATH, code = http.client.NOT_FOUND, headers = headers)
        
    #The page exists
    self.sendResponse(code, headers)
    for data in self.yieldFile(path):
      self.handler.wfile.write(data) #Incrementally writes data back to web
        
  def redirectFile(self, group, path, headers = None):
    if not headers:
      headers = {}
    headers["Location"] = path
    return self.sendFile(group, self.NO_PATH, code = http.client.FOUND, headers = headers)
    
class PostHandler(Handler):
  pass
  
class GetHandler(Handler):
  def do_selectionScreen(self, _): #We don't care for group
    log.web.debug("Sending Selection Screen")
    basicFile = self.loadFile(self.genFiles[self.fileName])
    if not basicFile: raise ValueError("Could not load selection screen!")
    
    content = ""
    for group in Groups.getGroupList(groupType = Groups.MainGroup): #Get a list of all the main groups
      content += \
      """<tr onclick="document.location = '{group}/index.html'">
        <td valign="middle" style="text-align:center"><p style="font-size:110%;margin:5pt">{groupName}</p><p style="font-size:100%;font-style:italic;color:#008800;margin:5pt">Group {group}</p></td>
        <td width = 1pt><img src="{groupImage}" style="vertical-align:middle;width:90px"></td>
      </tr>""".format(group = group.getID(), groupName = group.getName(), groupImage = group.image or "favicon.ico")
      
    basicFile = basicFile.replace(self.STR_CONTENT, content)
    
    self.sendResponse() #Send good response
    self.handler.wfile.write(basicFile.encode(self.ENCODING))