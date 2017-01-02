#Handles "Groups" as well as subgroups and event groups
#Each "Group" can be passed a message and can act on it. Data is passed via an interface between the mainServer and Groups
#Each subgroup will be treated as a group and can access all functions of the main group except delete
#Groups will have access to local information about each "User", and their functions

import dateutil.parser
import json
import pickle
import random
import re
import time

import Commands
import Events
import Files
import Jokes
import Logging as log
import MsgSearch
import Network
import Users

### Methods common to all groups on a server

#Dict of [ID] : group reference
groupDict = {}
#Dict of [groupID] : group reference
groupIDDict = {}

#The common name for a save file in a group's folder
SAVE_FILE_NAME = "groupData"

def getGroup(groupIdent):
  try: #First tries to get internal id
    return groupDict[groupIdent]
  except KeyError:
    #Then tries to get GroupMe ID
    try:
      return groupIDDict[groupIdent]
    except KeyError:
      #If neither, return None
      return None

#Searches through Group's "groupDict" for SubGroups. Then checks if the subgroup has a parent that is the given group
#PRE : group must be a "Group" object or derived class that is not a "SubGroup" or derived class
#POST: If the group was a Group, returns a list of SubGroups with the group as a parent. Otherwise returns [] (empty list)
def getChildren(group):
  toRet = []
  if not isinstance(group, Group) or isinstance(group, SubGroup): return toRet
  for groupNum in groupDict:
    if groupNum != group.ID:
      testGroup = groupDict[groupNum]
      if isinstance(testGroup, SubGroup) and testGroup.parent == group:
        toRet.append(testGroup)
  return toRet
  
#POST: Returns a valid group if the file was valid. None otherwise
_folderCache = {}
def loadGroup(folder):
  if type(folder) == int:
    folder = "Group "+str(folder)
  try:
    loadedGroup = _folderCache[folder]
    log.group("Group already loaded, returning group:", loadedGroup)
    return loadedGroup
  except KeyError:
    pass #Just continue loading
  try:
    groupNumber = int(re.search("\d+", folder).group())
    log.group("Loading Group:", groupNumber)
  except AttributeError:
    raise RuntimeError("Group Folder '"+folder+"' does not have a group number")
  try:
    with open(Files.getFileName(Files.join(folder, SAVE_FILE_NAME))) as file:
      groupType = Files.read(file)
      log.group("Group Type:",groupType)
      newGroup = globals()[groupType](groupNumber).load(file) #Load arbitrary class
      _folderCache[folder] = newGroup #Save it to a cache so we cannot load twice
      return newGroup
      #except (KeyError, TypeError, AttributeError) as Error: #I actually think I want this to be a halting error.
      #  log.error("Failed to properly load group file:", Error)
  except FileNotFoundError: #The group was improperly initialized/saved
    log.group.error("Group had no load file. Deleting folder")
    Files.deleteFolder(folder)
  
#Makes a new group known to the overall module, assigns a new group id if the group does not already have one
#NOTE: Will simply pick the next number not registered. Assumes that new groups will not be made before group loading is complete
def groupRegister(groupObj, firstID = None):
  if firstID or not groupObj.ID: #New group, needs an ID
    if type(firstID) != int: firstID = 1
    assignNumber = firstID #On new object creation, we can get a group after a certain number (for example, allowing subgroups to load after their parents)
    while assignNumber in groupDict:
      assignNumber += 1
    groupObj.ID = assignNumber
    
  if type(groupObj.ID) is not int:
    raise TypeError("Tried registering group with non-integer ID:" + repr(groupObj.ID))
    
  if not groupObj.ID in groupDict:
    groupDict[groupObj.ID] = groupObj
    
  if groupObj.groupID:
    groupIDDict[groupObj.groupID] = groupObj
    
#This goes through all the registration dictionaries and removes traces of the group
#PRE: "tables" must be a list of dicts
def groupDeregister(groupObj , tables = [groupDict, groupIDDict]):
  if getChildren(groupObj):
    raise RuntimeError("Cannot deregister " + repr(groupObj) + " because it has children")

  #These should be dicts
  for table in tables:
    for i in table.copy():
        if table[i] == groupObj:
          del table[i]


### Group List Acquisition Functions ###

#Returns a list of all loaded groups. If "groupType" is specified, it should be a Class inherited from Group.
#The object returned is safe to have groups deleted from
def getGroupList(groupType = None):
  if not groupType:
    return list(groupDict.values())
  if issubclass(groupType, Group):
    return [group for group in groupDict.values() if isinstance(group, groupType)]
  else:
    raise TypeError("getGroupList expected a groupType inherited from Group, got " + str(groupType))
  
          
def getSortedList(groupType = None, key = None):
  return sorted(getGroupList(groupType), key = key or Group.getID) #key or ... because cannot put Group. in argument list as group does not exist yet

#A "Group" represents an interface for a "base" group. So a "Group" object will keep track of all the data and users and references and subgroups that a group has.
#Group is also the network interface for all tasks that a group could do
class Group():
  overlord = None

  def __repr__(self):
    return "<Groups."+type(self).__name__+" object. ID: "+str(self.ID)+">"
      
  """
    Data Loading Model:
      When loading from file:
        __init__() - set default values, store pointers to helper objects (like handler, user list, etc)
          -- Object can now be passed as a reference
        load()     - replace default values with primitives loaded from file (like group numbers, user numbers, etc)
        init()     - replace primitives with meaningful associations (group numbers with group references, etc). Also load users here
          -- Group connections are inferred, all data is ready. Object cannot be used for web, no new data loaded
        postInit() - initialize helper files for use (like handler, etc). Also group is loaded into various associations
          --Group fully ready
          
      When creating new object:
        __init__() - Set all final values necessary
        Add any users/connections
        postInit() - Prepare for web use, etc
        save()     - Allocate file space for saving, record the existence of group in case of server stop
  """
      
  #ID can be None, and will be automatically assigned
  #Idiom for making new objects will be to do Group().save()
  def __init__(self, ID = None, groupID = None): #groupID is the GroupMe groupID, not internal (ID is internal)
    self.groupID = groupID
    self.name = None
    self.image = None
    self.password = None #This should be in MainGroup, but it doesn't save an attrTable and I have no way of changing it without breaking existing server
    #The owner is not necessary, but if there are multiple users with tokens, this will resolve issues
    self.owner = None #The owner is a token of the owner user
    self.bot   = None #This is the group's bot id that it uses to post messages
    #These are just save objects to be used by other modules
    self.analytics = {}
    self.commands  = {}
    
    self.markedForDeletion = False #Groups can get deleted. I want to delete the ones that don't exist, just not during initialization
    
    groupRegister(self, ID) #If no ID, will assign an id automatically
    
    self.folderPath = Files.getGroupFolder(self)
    self.filePath   = Files.getFileName(Files.join(self.folderPath, SAVE_FILE_NAME))
    
    #This UserList should be empty and just a reference to the object
    #Users should be loaded in postInit once we have gotten user data from internet
    self.users    = Users.UserList(self)
    self.handler  = Network.GroupMeHandler(self)
    self.commandBuilder = Commands.CommandBuilder(self)
    
  def init(self):
    self.users.loadAllUsers()
    
  def postInit(self): #We want group data to be loaded by "load" before we initialize all users
    if self.groupID:
      groupRegister(self) #Register new connections
      #Set up handler with groupID and info
      self.handler.postInit()
      try:
        #Must be done after handler initialized
        self.loadUsersFromWeb()
        if self.markedForDeletion:
          raise AssertionError("Group is marked for deletion, not trying to update bots")
         #If the IP address has changed since the last server restart
        if self.bot != None: #We don't do getBot here because that could actually create a new bot
          response = self.handler.getBotData()
          if response:
            try: #Filter out the bots for the one we have registered to this group
              ownBot = [bot for bot in response if bot['bot_id'] == self.getBot()][0]
            except IndexError: #If we haven't found one, we don't have a bot, and our data is faulty
              log.group.web("No external bot found, rectifying/creating new bot")
              if not self.handler.rectifyBot(response):
                self.bot = self.handler.createBotsly()
                if not self.bot:
                  log.error("Could not get bot for", self)
                  raise RuntimeError("BOT SHOULD EXIST FOR " + repr(self) + " BUT COULD NOT BE FOUND")
            else: #If the bot we found doesn't have the proper ip address, update it's ip address
              if ownBot['callback_url'] != Network.getIPAddress():
                log.group("IP has changed! Updating bot id")
                self.handler.updateBots(self.getBot())
          
        #After all that is done, update the message list
        MsgSearch.getSearcher(self).GenerateCache()
      except ConnectionError: #Indicates internet is down
        log.group.error("Failed to update users from web")
    else:
      log.group.error("WARNING: Group", self.ID,"has no groupID")
    
    self.save()
    
  def deleteSelf(self):
    log.group(type(self),self.ID,"deleting itself")
    log.group("Deregistering self")
    groupDeregister(self)
    log.group("Deleting Folder")
    Files.deleteFolder(Files.getGroupFolder(self))
  
  ### Utility Functions ###
  
  def getName(self):
    return self.name if self.name else "Group " + str(self.ID)
    
  def setName(self, name):
    self.name = name
    
  def getID(self):
    return self.ID
    
  ### Group Functions ###
    
  def getBotMaster(self): #Return the first available BotMaster
    if self.owner: #First give the "owner" if we have one
      return self.owner
      
    for user in self.users:
      if user.token:
        return user.token
    log.group.error("WARNING: Group has no BotMaster upon request")
    return None #If we have no botmasters, give them none
    
  def getSubGroupMaster(self):
    log.group("Getting subgroup BotMaster. Has Overlord: ", bool(Group.overlord))
    if Group.overlord:
      return Group.overlord
      
    return self.getBotMaster()
    
  def setOwner(self, user):
    if type(user) == str:
      self.owner = user
      return
    if isinstance(user, Users.User):
      self.owner = user.token
      return
      
  #If the group has no bot, it will automtically create one
  def getBot(self):
    if not self.bot:
      testID = self.handler.getBotFromWeb()
      if testID:
        self.setBot(testID)
      else:
        response = self.handler.createBotsly()
        if response:
          self.setBot(response)
        else:
          log.group.error("COULD NOT GET BOT FOR GROUP", self.ID)
    return self.bot

  def setBot(self, bot):
    if type(bot) != str:
      raise TypeError("bot for group " + repr(self) + " must be a str, got " + str(type(bot)))
    self.bot = bot
    
  ##TODO
  #I'm not sure how I want to implement this while taking the userList into account.
  #Because the userList makes userMimics on add, but we just have the dict when we add, and I don't want to mess with the dict
  #def addUser(self):
  #  pass
    
  #This is for internal removing of users
  #In this class, because MainGroups need to check their subgroups on user removal
  def removeUser(self, userObj):
    self.users.removeUser(userObj)
    
  #Should not be overridden
  def handleMessage(self, message):
    #First Record Data
    #Each group will get a "searcher" assigned it that loads all the group's messages and can search through them on command
    MsgSearch.getSearcher(self).appendMessage(message)
    
    if message.sender_type == "bot": return #We don't care what bot has to say, only record that it did
    #log.network("Handling message: ", message) #Really want to see this for now while handling stuff
    
    self.buffer = ""
    
    if message.text.lower() == "bot?": #Classic test
      self.buffer += "Yes? \U0001f604"
    
    self._handleMessage(message)
    
    #Handle user commands
    #NOTE: GROUPS DERIVED FROM OTHER CLASSES WITH DIFFERENT HANDLING SPECIFICATION SHOULD OVERRIDE commandBuilder IN __init__ TO BE OF THE APPROPRIATE TYPE
    commandList = self.commandBuilder.buildCommands(message)
    commandNum = 0
    for command in commandList:
      if not command.message.strip(): #If there isn't actually any text with the command
        continue
        
      commandNum += 1
      if len(commandList) > 1:
        if commandNum > 1: #Add in a newline if on the second or more command
          self.buffer += "\n"
        self.buffer += str(commandNum) + ". "
        
      #Handle the command, add its text to the buffer (or an explanation if in series with others)
      self.buffer += (command.handle() or ("Command returned no text" if len(commandList) > 1 else ""))
            
    #When all message handling is done
    if self.buffer:
      self.handler.write(self.buffer.rstrip())
      
    #Post all facts the user may be subscribed to
    if message.sender_type == "user": #Only if it is user, not system
      Jokes.postReleventJokes(self.users.getUserFromID(message.user_id), message.text)
    
  #This is for things specific to a certain type of group. Like handling events for MainGroups
  #NOTE FOR SUBCLASSES: Subclasses should do super() after their own handling
  #This stuff is in the parent class so that subclasses can just "return" and stop this processing from happening
  def _handleMessage(self, message):
    if message.isSystem():
      #Possibly split this into the Commands module
      nameChange = " changed name to "
      if nameChange in message.text:
        nameList = message.text.split(nameChange, 1)
        person = self.users.getUser(nameList[0]) #Get the user from the old name
        log.command.web("Got a name update for",person," --> ",nameList[1])
        if person:
          person.addName(nameList[1])
        return #Don't need to check any other messages if it was this one
        
      #If we added a new user, or removed a user
      if ("to the group" in message.text and "added" in message.text) or ("from the group" in message.text and "removed" in message.text):
        self.loadUsersFromWeb()
        
    
  ### Networking Functions ###
  
  #Not only loads users, also loads group name
  def loadUsersFromWeb(self):
    log.group.web("Group",self.ID," downloading group member data")
    if not self.groupID: #If we can't load, don't load
      raise AttributeError("Group " + str(self.ID) + " could not load group data, no groupID")
    groupData = self.handler.get("groups/"+self.groupID)
    if groupData.code == 404: #If our group does not exist any more
      self.markedForDeletion = True
      log.group.error("Group no longer exists. Recommend deleting group",self.ID)
     
    if groupData.code == 200:
      loadedList = [] #List of objects to check
      updateList = [] #This is just a list of names
      self.setName(groupData['name']) #Store the name the group has for future reference
      try: self.image = groupData['image_url'] #Try to get this if it exists (should exist, can't be bothered to check)
      except KeyError: pass
      for user in groupData['members']:
        #log.group.web("Updating user", '"'+user['nickname']+'"')
        updateList.append(user['nickname'])
        userObj = self.users.updateUser(user)
        loadedList.append(userObj)
        
      log.group.web("Users loaded:", ",".join(updateList))
        
      for userObj in self.users.userList.copy():
        if userObj not in loadedList:
          log.group.web(userObj,"does not exist on web, deleting user data")
          self.removeUser(userObj) #If they don't exist on the web, we shouldn't save their data

    else:
      log.group.error("Group unable to get member data from the web. Code:",groupData.code)
    
  ### Saving and Loading ###
  
  #This is the save that should be used normally
  #"basic" save should be used only during __init__, to make sure that the group exists so it's type can be read
  def save(self): #Method for saving a group and its data
    log.save("Saving:", self)
    with Files.SafeOpen(self.filePath, "w") as file:
      file.write(type(self).__name__+"\n")
      self._save(file)
    return self

  def _save(self, writeHandle): #This is where you have class specific saving things.
    Files.saveAttrTable(self, writeHandle, ["groupID", "name", "image", "password", "owner", "bot", "analytics", "commands"])
      
  def load(self, fileHandle): #Can load necessary data from file here
    Files.loadAttrTable(self, fileHandle)
    return self


class MainGroup(Group):
  def __init__(self, ID = None, groupMeID = None):
    super().__init__(ID, groupMeID)
    
    self.password = None
    
    #A dict of eventGroups of the form groupID : groupReference
    self.eventGroups = {}
    
  def init(self):
    super().init()
    #Initialize the event groups to their proper group references
    self.eventGroups = {key : getGroup(self.eventGroups[key]) for key in self.eventGroups}
    
  def postInit(self):
    super().postInit()
    
    if not Events.IS_TESTING:
      #We need to scan the group for new events that we don't have
      log.group.debug(self,"checking for events")
      
      events = self.handler.getEvents()
      if events:
        #Check if we need to create groups
        for event in events:
          if event['event_id'] not in self.eventGroups:
            log.group.debug("Creating new event group for event", event['name'])
            group = self.newEventGroup(event)
            if not group:
              log.group.error("COULD NOT MAKE NEW EVENT GROUP FOR EVENT", event," in ",self)
          else:
            log.group.debug("Group exists, updating group")
            self.eventGroups[event['event_id']].updateEvent(event) #If it already exists, give it new information
         
        #Check if we need to delete groups for events that no longer exist
        idList = [event['event_id'] for event in events]
        for event in list(self.eventGroups.keys()):
          if event not in idList:
            log.group.debug("Event no longer exists, trying to delete")
            self.eventGroups[event].deleteSelf()
            
      #Check if we need to delete groups for events that are over
      self.checkForEndedEvents()
    
  def getPassword(self):
    return self.password or "testPassword"
    
  def setPassword(self, password):
    if type(password) == str and len(password) > 0:
      self.password = password
      self.save()
      return True
    return False
    
  #Note: If a user leaves the mainGroup, the user's eventGroup counterparts will have no knowledge of the user's address, token, or other data
  def removeUser(self, userObj):
    #First check all our subgroups and make user objects for them
    log.group(self,"removing user",userObj,"from all eventGroups")
    for group in self.eventGroups.values():
      userMimic = group.users.getUserFromID(userObj.ID)
      if userMimic and isinstance(userMimic, Users.UserMimic): #If we have a userMimic of our user in eventGroup
        webUsers = group.handler.getUsers()
        for user in webUsers:
          if user['user_id'] == userObj.ID:
            log.group.web("Found user in",group, "making new user for them")
            group.users.removeUser(userMimic)
            group.users.updateUser(user, allowMimics = False)
    
    super().removeUser(userObj)
    
  """Example Events Response: Request Events
  {"response":{"events":
  [{"name":"Test Event Please Ignore",
    "description":"Test Description",
    "location":{"name":"Test Location"},
    "start_at":"2016-07-12T17:00:00-05:00", 
    "end_at":"2016-07-12T17:15:00-05:00",
    "is_all_day":false,
    "timezone":"America/Chicago",
    "reminders":[],
    "conversation_id":"14320017",
    "event_id":"6aac6b3721b5491fbf8c854e32991918",
    "creator_id":"27094908",
    "going":["27094908"],
    "not_going":[],
    "created_at":"2016-07-12T21:55:32Z",
    "updated_at":"2016-07-12T21:55:32Z"}]
    },"meta":{"code":200}}
  """
  """Example Event Payload: Create
  {"name":"2nd Test Event","description":"asdfasdfasdf","location":{"name":"Another location"},"start_at":"2016-07-12T17:00:00-05:00","end_at":"2016-07-12T17:15:00-05:00","is_all_day":false,"timezone":"America/Chicago","reminders":[900]}
  Response:
  {"response":{"event":{"name":"2nd Test Event","description":"asdfasdfasdf","location":{"name":"Another location"},"start_at":"2016-07-12T17:00:00-05:00","end_at":"2016-07-12T17:15:00-05:00","is_all_day":false,"timezone":"America/Chicago","reminders":[900],"conversation_id":"14320017","event_id":"4c826c4b480e43a1bc87640ad513868c","creator_id":"27094908","going":["27094908"],"not_going":[],"created_at":"2016-07-12T21:58:59Z","updated_at":"2016-07-12T21:58:59Z"},"message":{"attachments":[{"event_id":"4c826c4b480e43a1bc87640ad513868c","type":"event","view":"full"}],"avatar_url":"https://i.groupme.com/960x768.png.c9510bef4adf485bad85f5626afcb8a5","created_at":1.468360739e+09,"favorited_by":[],"group_id":"14320017","id":"146836073914421230","name":"Dan K Maymays","sender_id":"27094908","sender_type":"user","source_guid":"5f85eb6623be4e2f85961a43a6e9fb2b","system":false,"text":"Dan K Maymays created event '2nd Test Event' https://s.groupme.com/7mukgLu","user_id":"27094908"}},"meta":{"code":201}}"""

  def _handleMessage(self, message):
    
    self.checkForEndedEvents()
    
    ### Everything to do with modifying events and their users ###
    if message.hasAttachments("event"):
      log.command("Running Event Code")
      originalEvent = message.getAttachments("event")[0]['event_id']
      if message.isUser() and "created event" in message.text: #This should be sent by a user
        eventData = self.handler.getEventData(originalEvent)
        if eventData:
          self.newEventGroup(eventData)
          return
        log.group.error("No event found in group for event ID",originalEvent['event_id'])
      elif message.isSystem(): #System informs people are going to/not going to/undecided about events
        if "canceled" in message.text:
          try:
            log.group.debug("Event cancelled. Deleting group associated with",originalEvent)
            self.eventGroups[originalEvent].deleteSelf()
            log.group.debug("Deletion succeeded")
          except KeyError:
            log.group.debug("Deletion Failed. Group is not a child of receiver")
          return
        else:
          for string in ['is going to', 'is not going to']:
            if string in message.text:
              userString = message.text[:message.text.rfind(string)]
              try:
                group = self.eventGroups[originalEvent]
              except KeyError:
                log.group.error("ERROR: No event group for event " + originalEvent + " not adding/removing users")
                return
              log.group("Removing" if "not" in string else "Adding","user '"+userString+"' for event",group)
              if "not" in string:
                #User may not exist in other group due to timing delays or what not, but should definitely exist in this group
                user = group.users.getUserFromID(self.users.getUser(userString).ID)
                if user:
                  group.removeEventUser(user)
                else:
                  log.group.debug("Could not find user '"+userString+"' in event group, not removing")
              else:
                group.addEventUsers(self.users.getUser(userString))
              break #Don't bother with other one if not done
          return
      elif message.isCalendar(): #Calendar sends event update notifications
        eventData = self.handler.getEventData(originalEvent)
        if eventData:
          try:
            self.eventGroups[eventData['event_id']].updateEvent(eventData)
          except KeyError:
            log.group.error("Tried updating event but event did not exist. Creating new instead")
            self.newEventGroup(eventData)
        
    super()._handleMessage(message)

  #POST: On successful group creation, returns the group object. If group already exists, returns the group from self.eventGroups
  #      On failure returns None
  def newEventGroup(self, eventData):
    if eventData['event_id'] in self.eventGroups:
      log.group("We already have a group for this event. Not creating group")
      return self.eventGroups[eventData['event_id']] #Group has been created. it just already exists
    #else
    
    if Events.IS_TESTING:
      return None #If testing we can't create
    
    log.group("Creating new event group!")
    groupOwner = self.getSubGroupMaster()
    self.handler.poster = groupOwner #A little hacky, but whatevs
    response = self.handler.createGroup(eventData['name'])
    self.handler.poster = self.getBotMaster()
    if response.code == 201: #If group was created successfully
      try:
        eventGroup = EventGroup(ID = self.ID, groupMeID = response['id'], parent = self)
        eventGroup.setOwner(groupOwner) #This just sets which token to use if there is a group with multiple
        eventGroup.postInit()
        
        if not random.randint(0,10):  #If the number is 0. 10% chance
          eventGroup.handler.changePosterName("Tester McTestosterone")
          
        post = eventGroup.handler.write
        post(("Description: "+eventData['description']) if "description" in eventData else "Welcome to the new event group! I'm here too!")
        try:
          locDict = eventData["location"]
          post("Location: " + (locDict["address"] if "address" in locDict else locDict["name"]))
        except KeyError:
          log.group("Event has no location")
        post("Have a joke!")
        Jokes.joke.postJoke(eventGroup)

        eventGroup.updateEvent(eventData) #Add in users that are going to group
        
        self.eventGroups[eventData['event_id']] = eventGroup
        self.save()
        log.group("Finished new event group!")
        return eventGroup
      except Exception as e:
        log.group.error("FATAL ERROR IN EVENT GROUP CREATION. Deleting group")
        eventGroup.deleteSelf()
        raise e
    else:
      raise RuntimeError("Could not create event group: " + str(response.code))
      
   #Can delete eventGroups
  def checkForEndedEvents(self):
    for event in list(self.eventGroups.keys()):
      group = self.eventGroups[event]
      if group.end_at and group.end_at < time.time(): #If the group's time has passed
        log.group.debug("Event time has passed, deleting", group)
        group.deleteSelf()
    
  def _save(self, handle):
    super()._save(handle)
    #Rather than saving group references, we save IDs, then load the connections on postInit
    json.dump({key : self.eventGroups[key].ID for key in self.eventGroups}, handle)
    handle.write("\n")
    
  def load(self, handle):
    #Load the super's saved items
    super().load(handle)
    #Load our eventGroups
    self.eventGroups = json.loads(Files.read(handle)) #This will be turned into actual groups in .init()
    return self
    
  def deleteSelf(self, force = False):
    if force:
      super().deleteSelf()
    else:
      log.group.error("MainGroup object refuses to be deleted")
    

    
#A "Subgroup" is just a group tied to a "Group" object. It records data tied in with the base group (user analytics are tied to the base group, not the subgroup)
class SubGroup(Group):
  #So we can have the parent's data on analytics and commands
  def __getattr__(self, name):
    if name != "parent" and isinstance(self.parent, Group):
      if name == "analytics" or name == "commands":
        return getattr(self.parent, name)
    raise AttributeError("'"+type(self).__name__+"' object has no attribute '"+name+"'")

  def __init__(self, ID = None, groupMeID = None, parent = None):
    super().__init__(ID, groupMeID)
    
    del self.analytics #We don't want to have reference to these.
    del self.commands  #They are data handled by the parent group
    
    #parent should be set on __init__. Will not be set on load, and should be set in postInit after all groups have been loaded
    #during load, parent will be set to an integer representing the parent number
    self.setParent(parent)
    
  #PRE: Expects self.parent to contain the number key of the parent group
  def init(self):
    if type(self.parent) is int:
      self.setParent(groupDict[self.parent]) #Forms the actual in-memory conncetion to the parent group
    log.group("Group", self.ID," has parent", self.parent)
    
    super().init()
    
    #Now that all associations have been formed, we can load references
    for user in list(self.users):
      if isinstance(self, Users.UserMimic):
        parent = self.parent.users.getUser(user._tempID, idOnly = True)
        if not parent: raise RuntimeError("UserMimic in Group " + str(self.ID) + " could not find parent from ID " + user._tempID)
        user.setParent(parent)
    
  #If parentGroup is not a subgroup, self.parent will be set to it. Otherwise, TypeError is raised
  def setParent(self, parentGroup):
    if isinstance(parentGroup, SubGroup):
      raise TypeError("Error when setting parent. Parent cannot be of type " + str(type(parentGroup)) + " derived from 'SubClass'")
    self.parent = parentGroup
    
  
    
  def _save(self, handle):
    super()._save(handle)
    Files.write(handle, str(self.parent.ID))
    
  def load(self, fileHandle):
    super().load(fileHandle)
    del self.analytics #We don't want to have references to these
    del self.commands  # ^^
    self.parent = int(Files.read(fileHandle))
    log.save("Group ID set on subgroup load:", self.parent)
    
  def deleteSelf(self):
    super().deleteSelf()
    if self.groupID:
      #Note: This also deletes any bots associated with the group
      log.group("Removing GroupMe Group")
      if self.handler.deleteGroup(self.groupID).code == 200:
        log.group("GroupMe group successfully deleted")
      else:
        log.group("GroupMe group deletion failed")
    
    
  
#An "EventGroup" is a specific type of "Subgroup" that is created specially for events, and has helper methods for that
class EventGroup(SubGroup):
  def __init__(self, ID = None, groupMeID = None, parent = None):
    super().__init__(ID, groupMeID, parent)
    self.end_at = None

    
  ### Event Functions ###
    
  def addEventUsers(self, usersList):
    if usersList:
      if type(usersList) != list: usersList = [usersList]
      for user in usersList.copy(): #First check if we have them already. Don't need to add if so
        if self.users.getUserFromID(user.ID):
          usersList.pop(usersList.index(user))
      if self.handler.addUsers(usersList).code == 202:
        for member in usersList:
          #For all the users added, add in a mimic of them from the other group
          newMimic = Users.UserMimic(self, member)
          newMimic.GMName = member.GMName or member.realName #This is what the name is when adding to group
          self.users.addUser(newMimic)
  
  def removeEventUser(self, user):
    if user.group == self:
      log.group("Removing user",user,"from event group",self)
      if self.handler.removeUser(user):
        self.users.removeUser(user)
        log.group("Remove succeeded")
      else:
        log.group("Removal failed")
    
  def updateEvent(self, eventData):
    log.group("Updating",self,"from event data")
    
    self.end_at = dateutil.parser.parse(eventData['end_at']).timestamp() #This is an integer similar to time.time()
    
    log.group("Searching for users to add")
    toAdd = []
    for id in eventData['going']:
      if not self.users.getUserFromID(id):
        toAdd.append(self.parent.users.getUserFromID(id))
       
    self.addEventUsers(toAdd)
    
    log.group("Searching for users to delete")
    for id in eventData['not_going']:
      if self.users.getUserFromID(id):
        self.removeEventUser(self.users.getUserFromID(id)) #Just remove them straight out. We cannot do multiple calls
    
    log.group("Checking for group attribute changes")
    toAdd = {}
    if 'name' in eventData:
      if eventData['name'] != self.name: #We don't need to update it if we already have this name
        toAdd['name'] = eventData['name']
    if 'image_url' in eventData: 
      if eventData['image_url'] != self.image:
        toAdd['image'] = eventData['image_url']
    if toAdd:
      if self.handler.updateGroup(**toAdd).code == 200: #Unpack the name and image_url if they exist
        #Then if we were setting them above, set them here
        if 'name' in toAdd:
          self.setName(toAdd['name'])
        if 'image' in toAdd:
          self.image = toAdd['image']
    
    
    self.save()
    
  def _save(self, handle):
    super()._save(handle)
    Files.saveAttrTable(self, handle, ['end_at'])
    
  def load(self, handle):
    super().load(handle)
    Files.loadAttrTable(self, handle)
    
  def deleteSelf(self):
    super().deleteSelf()
    log.group("Event group deregistering from parent event groups")
    groupDeregister(self, [self.parent.eventGroups])
    self.parent.save()
    
### Functions that get called periodically ###
def groupDailyDuties():
  log.group("Starting daily duties!")
  for group in getGroupList(MainGroup): #Go through all the MainGroups to check for events that have ended
    group.checkForEndedEvents()
    
  if Network.hasIPChanged():
    log.group("IP has changed! Updating bots of all groups")
    for group in getGroupList():
      if group.bot:
        group.handler.updateBots(group.bot)