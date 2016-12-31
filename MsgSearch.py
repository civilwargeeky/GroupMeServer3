#Keeps track of each Group's message and provides an interface to search through them
#Can seek to messages nearby each other
#Can be updated with new like counts and such

#MsgSearches should be tied to a "Group" and not a "SubGroup" or similar, but it should still differentiate between messages in a subgroup and the main group

import json #For loading and dumping messages to file
import time

import Commands
import Events
import Files
import Logging as log

_searcherList = {}

#Its okay if searchers do not exist at post-init. They will simply exist when needed
def getSearcher(group):
  try:
    return _searcherList[group.groupID]
  except KeyError:
    searcher = Searcher(group)
    searcher.load()
    _searcherList[group.groupID] = searcher
    return searcher

class Searcher():
  searchesFolder = "MsgSearchFolder" #The folder where all of the message archives are kept

  def __repr__(self):
    return "<MsgSearch."+type(self).__name__+" object for Group "+str(self.group.ID)+">"
    
  def __iter__(self): #So can do "for a in UserList"
    for message in self._messageList:
      yield Commands.Message(message)
      
  def __getitem__(self, key):
    if type(key) == slice:
      for i in range(key.start, key.stop, key.step or 1):
        yield Commands.Message(self._messageList[i])
    else:
      return Commands.Message(self._messageList[key])
    
  def __len__(self):
    return len(self._messageList)
    
  def __init__(self, group):
    self.group = group #Which Searcher this is
    self.fileName = Files.getFileName(Files.join(self.searchesFolder, "Group"+group.groupID))
    #Will only be set on load. This is the groupID of the parent group 
    self.parentID = None #(stored because many groups we save messages for groups that no longer exist on GroupMe)
    self._messageList = [] #This contains all known messages in chronological order. Values should all be standard strings
    self._hasLoaded = False
    
  ### File Functions ###
    
  #locationOverride used to save a msgSearch to another location
  def _save(self, locationOverride = None):
    location = locationOverride if locationOverride is not None else self.fileName
    if self._hasLoaded: #If hasn't loaded, nothing has changed yet (can't, hasn't been loaded)
      log.save.low("Saving",self)
      with Files.SafeOpen(location, "w") as file:
        try:
          Files.write(file, self.group.parent.groupID)
        except AttributeError:
          Files.write(file, "0") #In any case where there is no parent
        #Then write all messages
        json.dump(self._messageList, file)
        
  #For saving, just add self to the list of objects to be saved
  def save(self):
    Events.SyncSave().addObject(self)
  
  def load(self):
    if not self._hasLoaded:
      log.save.low("Loading",self)
      self._hasLoaded = True
      try:
        log.debug("Looking for file: ", self.fileName)
        with open(self.fileName, "r") as file:
          self.parentID = Files.read(file)
          self._messageList = json.load(file)
      except FileNotFoundError:
        log.save.debug("No file found for",self,", not loading")
      except ValueError:
        log.save.error("Invalid JSON Saving on server stop")
        
  
  ### Interface Functions ###

  def appendMessage(self, message): #Only to be used externally. Saves automatically
    #log.command.debug("We are not appending messages for now") #They work, but we aren't generating them yet
    #return NotImplementedError("Not generating caches for now")
  
    if not self._hasLoaded:
      self.load()
    if type(message) == str:
      message = json.loads(message) #In case its given as string
      
    self._messageList.append(dict(message)) #To dict because it should be a Commands.Message object
    self.save()
    
  ### Cache Functions ###
  
  #This generates the cache from scratch.
  def GenerateCache(self):
    self.load() #Loads if has not been loaded
    waitTime = 0.1 #0.1 Seconds between message batches
    log.analytics("Searcher generating cache for group " ,self.group)
    log.network.statePush(False) #There will be lots and lots of network traffic
    try:
      toStopAtID = self._messageList[-1]["id"]
    except IndexError:
      toStopAtID = None #Indicates there are no messages
    
    #Because the cache is in ascending chronological order, we must make a seperate list of new messages, reverse, and then update the cache afterward
    toPlace = []
    shouldContinue = True #Used in message processing to signal we found our last found message
    nextSearch = "" #The id to search from before_id next
    startCount = None #These are used to see if any messages were sent while we were indexing
    endCount   = None 
    while shouldContinue:
      #We get the last 100 messages from groupMe. There isn't much difference in time getting a hundred vs getting one, so its not worth to check if we are up to date
      #These messages come in in newest-oldest ordering
      response = self.group.handler.get("/".join(("groups",self.group.groupID,"messages")), query = {"limit":100, "before_id":nextSearch})
      if response.code == 200:
        messageStack = response['messages']
        nextSearch = messageStack[-1]['id']
        endCount = response['count']
        if startCount == None: startCount = endCount #Only update if we haven't done any messages yet
        for i in range(len(messageStack)):
          if messageStack[i]['id'] == toStopAtID:
            shouldContinue = False
            messageStack = messageStack[:i] #Only add the messages we don't have yet
            break
        toPlace.extend(messageStack) #Add more messages to extend later (in newest-oldest order)
        #Print out information on how many messages we have
        log.analytics("Acquiring {:5} / {:5}".format(len(toPlace), response['count'] - len(self._messageList)))
      elif response.code == 304: #If we have hit the end of messages
        break #Don't need to do anything else now, just add what we have
      elif response.code == 500:
        log.analytics.low("Hit message limit, sleeping")
        time.sleep(1) #This usually means we are sending too many messages at once
      else:
        raise RuntimeError("ERROR IN GENERATE CACHE: RECEIVED response.code " + str(response.code))
        
      if Events.IS_TESTING and len(toPlace) >= 500: #During testing, we want this to end sometime soon
        break
        
    #Getting here means we have collected all the messages we can
    toPlace.reverse() #Get all messages to append in oldest-newest order
    
    #It's possible we want it this way if we ever do anything else in appending the message
    #for message in toPlace: 
    #  self.appendMessage(message)
      
    self._messageList.extend(toPlace) #Add all messages to cache
    self.save()

    log.network.statePop() #Reset from false
    
    if startCount != endCount:
      log.analytics("Messages were sent while updating messages, we'll have another go at it")
      self.GenerateCache()
