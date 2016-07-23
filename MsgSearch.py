#Keeps track of each Group's message and provides an interface to search through them
#Can seek to messages nearby each other
#Can be updated with new like counts and such

#MsgSearches should be tied to a "Group" and not a "SubGroup" or similar, but it should still differentiate between messages in a subgroup and the main group

import json #For loading and dumping messages to file
import time

import Commands
import Files
import Logging as log

_searcherList = {}

#Its okay if searchers do not exist at post-init. They will simply exist when needed
def getSearcher(group):
  try:
    return _searcherList[group.ID]
  except KeyError:
    searcher = Searcher(group)
    searcher.load()
    _searcherList[group.ID] = searcher
    return searcher

class Searcher():
  def __repr__(self):
    return "<MsgSearch."+type(self).__name__+" object for Group "+str(self.group.ID)+">"
    
  def __iter__(self): #So can do "for a in UserList"
    for message in self._messageList:
      yield Commands.Message(message)
      
  def __getitem__(self, key):
    return self._messageList[key]
    
  def __len__(self):
    return len(self._messageList)
    
  def __init__(self, group):
    self.group = group #Which Searcher this is
    self.fileName = Files.getGroupFileName(group, "messageLog")
    self._messageList = [] #This contains all known messages in chronological order. Values should all be standard strings
    self._hasLoaded = False
    
  ### File Functions ###
    
  def save(self):
    if self._hasLoaded: #If hasn't loaded, nothing has changed yet (can't, hasn't been loaded)
      log.save.low("Saving",self)
      with open(self.fileName, "wb") as file:
        for message in self._messageList:
          file.write(json.dumps(message).encode("unicode_escape"))
          file.write(b"\r\n")
  
  def load(self):
    if not self._hasLoaded:
      log.save.low("Loading",self)
      self._hasLoaded = True
      try:
        with open(self.fileName, "r", encoding = "unicode_escape") as file:
          for line in file:
            self._messageList.append(json.loads(line))
      except FileNotFoundError:
        log.save.debug("No file found for",self,", not loading")
          
  ### Interface Functions ###
          
  def appendMessage(self, message): #Only to be used externally. Saves automatically
    log.command.debug("We are not appending messages for now") #They work, but we aren't generating them yet
    return NotImplementedError("Not generating caches for now")
  
    if not self._hasLoaded:
      self.load()
    if type(message) == str:
      message = json.loads(message) #In case its given as string
      
    self._messageList.append(dict(message))
    self.save()
    
  ### Cache Functions ###
  
  #This generates the cache from scratch.
  def GenerateCache(self):
    self.load() #Loads if has not been loaded
    waitTime = 0.1 #0.1 Seconds between message batches
    log.network("Searcher generating cache for Group " + str(self.group.ID))
    log.network.statePush(False) #There will be lots and lots of network traffic
    try:
      lastID = self._messageList[-1]["id"]
    except IndexError:
      lastID = None #Indicates there are no messages
    
    #Placeholders
    messageStack = []
    lastMessage = {}
    while False:
      pass
      
      
    log.network.statePop() #Reset from false