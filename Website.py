#Interface for handling web requests and serving files
import datetime
import http.client
import json
import re
import os

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

def handleRequest(method, parsedUrl, headers, handler):
  if method == "POST":
    log.net.debug("Handling POST")
    return PostHandler(parsedUrl, headers, handler).handle()
  elif method == "GET":
    log.net.debug("Handling GET")
    return GetHandler(parsedUrl, headers, handler).handle()
  else:
    log.net.error("Cannot handle request of type", method)
    
class Handler:
  NO_PATH      = "noFile.html"
  DEFAULT_PATH = "index.html"

  def __init__(self, parsedUrl, headers, handler):
    self.handler = handler
    self.url     = parsedUrl
    self.headers = headers
    groupNum = re.search("\AGroup (\d+)", self.url.path.lstrip("/"))
    self.group = Groups.getGroup(int(groupNum.group(1))) if groupNum else None
    
    #log.debug("Group: ", self.group)
    log.net.low("New Handler for Url: ", self.url)
    
  def handle(self):
    fileName = os.path.normpath(self.url.path)
    log.net("File Requested: '"+fileName+"'")
    return self.sendFile(fileName)
    
  def existsFile(self, path):
    return os.path.exists(path) and os.path.isfile(path)
    
  def yieldFile(self, path):
    with open(path, "rb") as handle:
      #yield handle.read() #Super simple way
      while True:
        data = handle.read(1024 * 256) #Don't load too much data at once.
        if not data: break #Check if any more data to read
        yield data #Return this bit of data
    
  #This will actually do the sending of the response over a handler
  #headers is response headers to send along with the request, NOT THE HEADERS WE GOT
  def sendFile(self, path, code = http.client.OK, headers = {}):
    path = path.strip("\\") #Strip these from both sides or else things mess up
    if not path: #If the path is blank
      return self.redirectFile(self.DEFAULT_PATH, headers)
      
    #log.debug("File requested for path: '"+path+"'")
    if not self.existsFile(path):
      
      path = os.path.join(DEFAULT_DIR, path)
      if not self.existsFile(path) and not path.endswith(self.NO_PATH): #We will always be able to access NO_PATH, but don't create an infinite loop
        log.net.error("Cannot find file for path '"+path+"', returning",self.NO_PATH)
        #return self.redirectFile(self.NO_PATH)
        return self.sendFile(self.NO_PATH, code = http.client.NOT_FOUND, headers = headers)
        
    #The page exists
    self.handler.send_response(code)
    for key in headers:
      self.handler.send_header(key, headers[key])
    self.handler.end_headers()
    for data in self.yieldFile(path):
      self.handler.wfile.write(data) #Incrementally writes data back to web
        
  def redirectFile(self, path, headers = {}):
    if not headers:
      headers = {}
    headers["Location"] = path
    return self.sendFile(self.NO_PATH, code = http.client.FOUND, headers = headers)
    
class PostHandler(Handler):
  pass
  
class GetHandler(Handler):
  pass