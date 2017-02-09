#Interface for Users in a GroupMe group. Each user stores data like analytics and is responsible for saving said data
#A "User" is tied to a "Group"

import json
import re

import Files
import Groups
import Logging as log
      
#A user without an id but not a token
#Contains methods for data-manipulation
class User():
  #This is a helper function that determines what kind of user is specified in a file, 
  #then delegates loading to the proper class
  # File Should Look Like:
  # BotMaster
  # key : value
  # key : value
  @staticmethod
  def loadUser(fileName, groupReference):
    with open(fileName) as file:
      userType = file.readline().rstrip() #First line will be type of user
      log.save.low("Loading ",userType,"from",fileName)
      return globals()[userType](groupReference).load(file) #Load arbitrary class

  _keyAddrDefault = "_main"

  def __repr__(self):
    return "<Users."+type(self).__name__+" object. Name: " + self.getName() + ">"
      
  #Needs a group reference, the ID can be set either in "load" or when user first loaded
  def __init__(self, group, groupMeID = None):
    if not isinstance(group, Groups.Group):
      raise TypeError("New user object must have a 'Group' object, was given ", str(type(group)))
  
    #Group reference
    self.group = group
    self.ID = groupMeID
    self.realName = None #Person's real name
    self.GMName = None #GroupMe Name
    self.token = None
    self.alias = []
    self.data = {} #Container for storing generic data about the user. Useful for other modules getting passed the user
    
    self._hasLoaded = False
  
  def getFileName(self):
    if not self.ID: log.error("Attempted to get file name for unloaded or unset user")
    return Files.getFileName(Files.join(Files.getGroupFolder(self.group), "Users", self.ID or "DEFAULT_USER"))
    
  #Just adds an alias. No name update required
  #POST: Returns True if the name did not exist, False otherwise
  def addAlias(self, name):
    if name not in self.alias:
      self.alias.append(name)
      self.save()
      return True
    return False
      
  def removeAlias(self, name):
    try:
      self.alias.pop(self.alias.index(name))
      self.save()
      return True
    except IndexError:
      log.user("Could not remove alias",name,"for",self.getName()+". Name could not be found")
      return False
    
  #Updates or sets the user's name, adding it to an alias list every time it is set
  def addName(self, name, realName = False):
    self.addAlias(name)
    if realName:
      self.realName = name
    else:
      self.GMName = name
    self.save()
    return True #Because this is used other places
    
  def addRealName(self, name):
    return self.addName(name, realName = True) #addName saves
     
  #Just checking for having this name
  def hasName(self, name):
    return name in self.alias
    
  #Returns a display name for a user. If preferGroupMe is true, will attempt to return the "GroupMe Name" before "Real Name"
  def getName(self, preferGroupMe = False):
    nameList = [self.realName, self.GMName]
    if preferGroupMe:
      nameList.reverse()
    for value in nameList:
      if value:
        return value
    return "User " + (self.ID or "Undefined")
    
  def getGMName(self):
    return self.getName(preferGroupMe = True)
    
  #Removes the given name, resetting realName if necessary
  #PRE: name is a string
  #POST: if name does not exist, IndexError. otherwise returns True if name removed, False if
  #        name was GMName and couldn't be removed.
  def removeName(self, name):
    if name == self.GMName:
      return False #Cannot remove groupMeName
    if name == self.realName:
      self.realName = None
    self.removeAlias(name) #Remove alias saves user
    return True
    
    
  #Just returns the string of the name along with "real name" if its the real name and "GM Name" if its the groupMe name
  #E.G. If someone's real name is Jorge, and we request Jorge, will return "Jorge ('Real Name')"
  def specifyName(self, name):
    return name+(" (Real Name)" if name == self.realName else "") + (" (GM Name)" if name == self.GMName else "")
    
  def setToken(self, token):
    if type(token) != str: raise TypeError("token must be of type str, not "+str(type(token)))
    self.token = token
    return self
    
  def getToken(self): return self.token
  
  def setAddress(self, address, addressType = None):
    if type(address) != str:
      raise TypeError("setAddress expected string, got " + str(type(address)))
    
    key = 'address'
    if key not in self.data:
      self.data[key] = {}
    if type(addressType) == str:
      self.data[key][addressType] = address
    else: 
      self.data[key][self._keyAddrDefault] = address
    self.save()
      
  def getAddress(self, addressType = None):
    key = 'address'
    try:
      if type(addressType) == str and addressType:
        return self.data[key][addressType]
      else:
        return self.data[key][self._keyAddrDefault]
    except KeyError:
      return False #If key error, we don't have the address requested
  
  def save(self):
    log.save.low("Saving",type(self).__name__,"data for", self.ID or self.getName())
    with Files.SafeOpen(self.getFileName(), "w") as file: #Will save data, first line being the class __name__
      Files.write(file, type(self).__name__)
      self._save(file)
    return self
    
  def _save(self, writeHandle): #This is where you have class specific saving things.
    Files.saveAttrTable(self, writeHandle, ["ID", "realName", "GMName", "token", "alias", "data"])
      
  #LOAD MUST RETURN SELF
  def load(self, fileHandle): #Can load necessary data from file here
    if not self._hasLoaded:
      Files.loadAttrTable(self, fileHandle)
      self._hasLoaded = True
    return self
    
  def delete(self):
    log.save.low("Saving",type(self).__name__,"data for", self.ID or self.getName())
    success = Files.deleteFile(self.getFileName())
    log.save.low("Deletion", "succeeded" if success else "failed")

#The user mimic will store only a few values for itelf, and resolve all other values to its parent
class UserMimic(User):
  def __init__(self, groupReference, parent = None):
    self._init = True #Signal to the metamethod that we are in init
    
    if parent != None and not isinstance(parent, User):
      raise TypeError("Parent of UserMimic must be user, not " + str(type(parent)))
    self._parentObj = parent #A reference to the mimic's parent
    
    #Things we store locally
    self.GMName = None
    self.group = groupReference
    self._tempID = None #This is for loading the ID
    
    self._init = False
    
  def __getattr__(self, name):
    if name == "parentObj": #A little bit of recursion. If we are searching for parentObj, then we have no parentObj...
      raise AssertionError
      
    try:
      if self._parentObj == None:
        raise AttributeError("'"+str(type(self).__name__)+"' object has no initialized parent. Cannot get '"+name+"'")
      else:
        return getattr(self._parentObj, name)
    except AssertionError:
      raise AttributeError("'"+str(type(self).__name__)+"' object has no attribute '"+name+"'")
    
  def __setattr__(self, name, value):
    #If we are not in init, and do not already have this value
    if name != "_init" and not self._init and name not in ["_parentObj","GMName","group","_tempID"]:
      setattr(self._parentObj, name, value) #Set value in parent
      return
    object.__setattr__(self, name, value) #Set own value
    
  def setParent(self, parent):
    if isinstance(parent, User):
      self._parentObj = parent
    else:
      raise TypeError("UserMimic cannot set parent to '"+str(type(parent))+"', must be 'User'")
      
  def getParent(self):
    return self._parentObj
    
  def _save(self, handle):
    Files.saveAttrTable(self, handle, ["GMName"])
    Files.write(handle, self.ID)
    
  def load(self, handle):
    Files.loadAttrTable(self, handle)
    self._tempID = str(Files.read(handle))
    #We should be loaded after the parent has loaded
    self._parentObj = self.group.parent.users.getUserFromID(self._tempID)
    return self
    
  
 
    
#This is a bot, who is tied to a "Group" and can post messages there
#As they are just IDs and methods, probably will just be loaded with data from a botmaster
class Bot():
  pass

#Class that is an interface for finding users
#NOTE on Savable Data: All connections are made on startup. The UserList does not save any data about users.
class UserList():
  def __iter__(self): #So can do "for a in UserList"
    for user in self.userList:
      yield user

  #On init, this is just an empty object with no users (even if there are users that can be loaded)
  #Users will be loaded after communication with internet
  def __init__(self, group):
    #Users will be "verified" when communicating with the server. 
    #People who do not exist will not usually be sent in requests for group members
    self.hasVerified = False
    self.group = group #Group reference
    
    self.dirName = Files.join(Files.getGroupFolder(self.group), "Users")
    
    #Note: position in userList is not static 
    self.userList = [] #This will be where users are normally stored
    self.IDDict = {}
    self.aliasList = {}
    
    #Creates folder if it does not exist
    Files.createFolder(self.dirName)
    
  ### User Manipulation ###
    
  #Expects local user data to be loaded already
  def loadAllUsers(self):
    files = Files.getFilesInDir(self.dirName)
    log.user("Loading {: 2} users for Group".format(len(files)), self.group.ID)
    for userFile in files:
      try:
        user = User.loadUser(userFile, self.group)
        self.addUser(user)
      except KeyError: #This means the data was corrupted on save
        log.user.error("Could not load user from file:",userFile,"is probably corrupted")
        
      
  def addUser(self, userObj):
    if userObj.ID in self.IDDict:
      raise RuntimeError("Tried to add duplicated user to group " + repr(self.group))
  
    if not userObj in self.userList:
      self.userList.append(userObj)
    self.IDDict[userObj.ID] = userObj
    return userObj
    
  def removeUser(self, userObj):
    if userObj in self.userList:
      self.userList.pop(self.userList.index(userObj))
    if userObj.ID in self.IDDict:
      del self.IDDict[userObj.ID]
    userObj.delete()
    
  #getUser expects "userIdent" to be either a user's id, or a string containing a user's groupMe name or real name
  #POST: If user found, returns a "User" object. On failure returns "None". Will raise TypeError if input is not a string
  def getUser(self, userIdent, onlyID = False):
    if type(userIdent) != str: raise TypeError("getUser expected string. Got " + str(type(userIdent)))
    try: #First try search by id
      return self.IDDict[userIdent]
    except KeyError:
      if not onlyID:
        userIdent = userIdent.lstrip("@") #Get rid of @tagging (possibly make it search GMNames first if this?)
        userIdent = userIdent.replace("'s", "") #Get rid of any possessives
        log.user("Searching string for member",userIdent)
        
        realNames = {}
        GMNames   = {}
        alii      = {} #Sounds better than aliases
        for user in self.userList:
          if user.GMName: GMNames[user.GMName] = user
          if user.realName: realNames[user.realName] = user
          for name in user.alias:
            if not name in alii:
              alii[name] = user
            
        def searchNames(searchDict):
          #Search through the input string for names, starting with the longest names first to avoid conflicts
          #E.G. If we have "Ian George" and "Ian George 4 Lyfe" we want to get "Ian George 4 Lyfe" first always
          for name in sorted(searchDict, key = len, reverse = True):
            log.user.low("Testing name:",repr(name))
            #Find a match for the name (between word breaks or an at sign) ignoring case. Also strip out all the punctation on the right so "\b" matches names like Jordan "4 Stillballs"
            if re.search(r"\b"+name.rstrip("\"'.,!?/\\")+r"\b", userIdent, re.IGNORECASE):
              log.user.debug("Found user:", searchDict[name])
              return searchDict[name]
          return False
         
        log.user.low("Searching names for GMNames")
        toRet = searchNames(GMNames)
        if toRet: return toRet
        log.user.low("Searching names for realNames")
        toRet = searchNames(realNames)
        if toRet: return toRet
        log.user.low("Searching names for alii")
        toRet = searchNames(alii)
        if toRet: return toRet
          
      log.user.low("Could not find user from identification", userIdent, "in Group", self.group.ID)
      return None
      
  def getUserFromID(self, userIdent):
    return self.getUser(userIdent, onlyID = True)
    
  #Right now this just executes the sort command, but in the future it could have sort types like "name", "length", etc
  def getUsersSorted(self, sortKey):
    return sorted(self.userList, key = sortKey)
      
  #WEB BASED
  #This updates the data and relations (like position in dicts and such) of a user from the dict returned by a web call
  def updateUser(self, userDict, allowMimics = True):
    #Update user's info
    user = self.getUserFromID(userDict['user_id'])
    if not user:
        log.user.web("Generating new user data for", '"'+userDict['nickname']+'"')
        if allowMimics and isinstance(self.group, Groups.SubGroup):
            log.user.low("Is loading for subgroup, using mimic")
            mimicParent = self.group.parent.users.getUser(userDict['user_id'])
            if mimicParent:
              log.user.low("Found mimic parent:",mimicParent)
              userObj = UserMimic(self.group, mimicParent)
            else: 
              log.user.low("Found no mimic parent, creating new user")
              userObj = User(self.group, userDict['user_id'])
        else:
          userObj = User(self.group, userDict['user_id'])
          
        user = self.addUser(userObj) #Create a new object and set it
        
    user.addName(userDict['nickname'])
    #If we have them registered, assume they exist in all dicts
      #... there aren't any dicts where information would change right now
    return user
    
    