#A nice interface for Commands.
#A command should be passed an unadultered message and return a "Command" object that has nice functions to act on message data

import re

import Events
import Groups #For type comparison
import Jokes  #For joke object getting
import Logging as log
import Network #For IP getting

class Message(dict):
  
  def __init__(self, responseDict):
    self.update(responseDict)
    for key in self: #Set all attrs as "self.groupID" or such
      setattr(self, key, self[key])
      
  def isUser(self):
    return self.sender_type == "user"
      
  def isSystem(self):
    return self.sender_type == "system"
    
  def isCalendar(self):
    return self.sender_type == "service" and self.sender_id == "calendar"
    
  def getUserString(self):
    if self.isUser():
      return self.name
    if self.isSystem():
      return "System"
    if self.isCalendar():
      return "Calendar"
    return "Unknown"
    
  #Returns the attachments list. If type_ is specified, will return only attachments matching that type in the list
  #  if there are no attachments matching type_, will return False
  def getAttachments(self, type_ = None):
    try:
      if type_ == None and self['attachments']: #If the attachment list is empty, do not return it, return false
        return self['attachments']
      elif type(type_) == str:
        toRet = []
        for attachment in self['attachments']:
          if attachment['type'] == type_:
            toRet.append(attachment)
        if toRet:
          return toRet
    except KeyError:
      pass #Will just return false
    return False
    
  #Simple alias
  def hasAttachments(self, type_ = None):
    return self.getAttachments(type_) != False

class CommandBuilder():
  def __init__(self, group):
    if not isinstance(group, Groups.Group):
      raise TypeError(type(self).__name__ + " object expected a Groups.Group object, got " + str(type(group)))
      
    self.group = group
    
    #List of strings that will trigger commands
    self.triggerStrings = ['botsly', 'bot']
    
  #This is called during __init__, but can also be called whenever the text changes
  def buildCommands(self, message):
    if not isinstance(message, Message):
      raise TypeError(type(self).__name__ + " object expected a Commands.Message object, got " + str(type(group)))
  
    #You can have several commands per message, so like
    # "@botsly addresses @botsly my address is whatever" would just execute two separate commands
    # each element is a two-list consisting of "name match" (bot, botsly, etc.) and the "command" (rest of string)
    commands = self.recurseFindCommand(message.text)
    toRet = []
    #All the commands will be initialized here
    for i in commands:
      #Tries to add command with strings and a user if the message had a user attached
      toRet.append(Command(self.group, i[1], i[0], self.group.users.getUserFromID(message.user_id)))
    return toRet
    
  #Recursively searches the string for trigger matches. Will start on right and work left, adding commands as it goes.
  #In the end, returns a list of two-lists of the form "name match" and "command"
  def recurseFindCommand(self, string, commandList = None):
    log.command.low("Entering recurse for",string)
    if not commandList: commandList = list() #Apparently, when you put a list as default argument, it's only evaluated once so the list was holding between calls
    matchFound = False
    highestIndex = None
    #However, we need to ensure that we have the command at the closest to the start of the string possible, so it can be recursed
    for trigger in sorted(self.triggerStrings, key = len, reverse = True):
      #log.debug("Testing",trigger)
      index = string.lower().rfind("@"+trigger)
      #log.debug("Match at ",index)
      if index >= 0 and (highestIndex is None or index > highestIndex):
        #log.debug("Index was","not set" if highestIndex is None else "higher")
        highestIndex = index
        matchFound   = True
        beforeString = string[:index].rstrip() #Remove space between previous and command
        nameMatch    = string[index:index+len(trigger)+1].lstrip("@")
        afterString  = string[index+len(trigger)+1:].strip() #Remove space between command, and any at end.
    if matchFound:
      commandList.append([nameMatch, afterString])
      return self.recurseFindCommand(beforeString, commandList)
      
    #If no more matches we can return the list of commands
    #reverse the list so they are in position order
    commandList.reverse()
    return commandList
   
def methodize(toGet): #I swear I'm not a protestant
  return toGet.replace(" ","_")
   
### Command Utiltites ###
def filterWords(string, wordList, replacement = ""):
  for word in wordList:
    string = re.sub(r"\b"+word+r"\b", replacement, string, re.I)
  return string

def stripPunctuation(string):
  return string.strip(".!?,:;'\"()")
  
def findWord(word, string):
  if type(word) == str:
    word = [word]
  if not word: return None
  for i in word:
    match = re.search(r"\b"+i+r"\b", string, re.I)
    if match: return match
  
def findMe(string):
  for word in ["me","my","I"]:
    match = findWord(word, string)
    if match:
      return match #If not found will return None
   
### Command Class ###
#In addition to message functions, this module will contain functions to respond to commands (and manipulate data that could be used in them)
"""
A command will contain the various parts of a command. So a typical command could like
      @[bot name] [verb] [recipient] [specifier(s)] [command] [target/details]   
E.g.  @[botsly] [set] [my] [] [address] to [this place]
      @[botsly] [what] is [Zoe]'s [college] [address]? []
      @[botsly] [tell] [] [5 blonde] [jokes] []
      @[botsly] [] [] [] [joke] []
So the command will be able to return .bot .verb .recipient .specifier .command .details

Each "command" will have 3 definitions. 
1. A string in the dict (plus other commands that could match)
2. A do_command function that sets all parameters and returns nothing
3. A handle_command function that will act on data, returning a string or None and possibly posting to the parent group
"""
class Command():

  #If sender is set, it should be a User object that is the default user for an action. Set if action detects "me" or similar
  def __init__(self, group, commandString, botString, sender = None):
    if not isinstance(group, Groups.Group):
      raise TypeError(type(self).__name__ + " object expected a Groups.Group object, got " + str(type(group)))
      
    self.commands = {name: None for name in [\
                     "version", "help", "address", "addresses", "joke", "name", "names", "human affection", "group password", "shutdown", "restart" \
                     ]}
    #Example: {"residence":"address"}
    self.commands.update({"jokes":"joke", r"facts?":"joke", r"pics?":"joke", "pictures?":"joke",
                          "called":"name", "love":"human affection"})
    
    self.group = group
    self.message = commandString
    self.bot = botString
    self.sender = sender
    
    #Things to be set by a command function
    self.verb         = None #The verb is kind of like a specifier but references what the action should be doing (setting, getting, etc.)
    self.recipient    = None #This is a string denoting the recipient of the action
    self.recipientObj = None #This will be a user object from a userlist
    self.specifier    = None #The specifier is some additional data about the command, like if we want blonde jokes or nerd jokes
    self.command      = None #This is not set by the called function
    self.details      = None #Details would be like the contents of the address, or the the name to set a new name to
    #Thsee are for left and right of command
    self.leftString   = None
    self.rightString  = None
    
    log.command.low("Command String:",self.message)
    for command in self.commands:
      log.command.low("Looking for command:", command)
      match = findWord(command, self.message)
      if match:
        methodName = "do_"+methodize(self.commands[command] or command)
        self.leftString  = self.message[:match.start()].rstrip()
        self.rightString = self.message[match.end():].lstrip()
        log.command.low("Left:",self.leftString)
        log.command.low("Right:",self.rightString)
        try:
          method = getattr(self, methodName)
          log.command.debug("Starting method", methodName)
        except AttributeError:
          log.command.error("No Command handling method found for",command)
        method()
        self.command = self.commands[command] or command
        log.command.low("Results of command:", self.formatSelf())
        break
    
  def formatSelf(self):
    return "<Command.Command object with \n" + "\n".join([name+": "+repr(getattr(self,name)) for name in ['verb','recipient','recipientObj','specifier','command','details']])+">"
    
  def setRecipient(self, fromString):
    if findMe(fromString):
      self.recipient = "me"
      self.recipientObj = self.sender
      return
      
    self.recipient = fromString.strip()
    self.recipientObj = self.group.users.getUser(fromString.lstrip("@")) if self.recipient else self.sender #So it defaults to the sender if you do like "address" it should return your address
    if not self.recipientObj: self.recipientObj = self.sender #It will also default to sender if we can't find any user (POTENTIALLY BAD)
    
  def handle(self):
    if self.command:
      methodName = "handle_"+methodize(self.command)
      try:
        method = getattr(self, methodName)
        log.command.debug("Handling",methodName)
      except AttributeError:
        log.command.debug("No handle function for method",methodName)
        return ""
        
      return method() #Return the string it returns
    else:
      senderName = "internet person"
      if self.sender:
        senderName = self.sender.getName(preferGroupMe = True)
      return "I'm sorry, " + senderName + " but I'm afraid I can't '"+filterWords(self.message, "me", "you")+"'"
      #return "I'm sorry, " + senderName + " but I'm afraid I can't do that"
  
  def do_version(self):
    with open("version.txt") as file:
      self.details = file.read().rstrip()
  
  def handle_version(command):
    return "BOTSLY FIRMWARE VERSION " + command.details
  
  def do_help(self):
    return
    
  def handle_help(command):
    mainString = "Try out the website! {}\n(Password: "+command.group.getPassword()+")"
    try:
      return mainString.format(Network.getIPAddress())
    except RuntimeError:
      IP = Network.readIPFile()
      if IP:
        return mainString.format(Network.readIPFile() + " (hopefully...)")
      return mainString.format("I have no idea what it is, but it probably exists! (Go yell at Daniel)")
  
  def do_address(self):
    self.details = filterWords(stripPunctuation(self.rightString), ["in","is", "to", "and"]).strip()
    
    remainingString = self.leftString.strip()
    if findWord("is", self.rightString):
      self.verb = "set"
    for word in ["set", "get", "what'?s?","where'?s?"]:
      match = re.search(r"\A"+word+r"\b", remainingString, re.I)
      if match:
        self.verb = "set" if word is "set" else "get" #Let them know for sure what it is
        remainingString = remainingString[match.end():].lstrip() #Take out the word we found
        break
    
    for word in Events.ADDRESS_MODIFIERS: #Goes through possible types of addresses, checking only at the end to get "College Address" but not "College Sophia's address"
      match = re.search(r"\b"+word+r"\Z", self.leftString.rstrip(), re.I)
      if match:
        self.specifier = word
        remainingString = remainingString[:match.start()].rstrip()
        break
        
    remainingString = remainingString.strip()
    self.setRecipient(remainingString)
    
  def handle_address(command):
    if command.recipientObj:
      name = command.recipientObj.getName()
      addressString = (command.specifier.title() + " " if command.specifier else "") + "Address"
      if command.verb == "set":
        command.recipientObj.setAddress(command.details, command.specifier)
        return addressString+" Updated:\n" + name + " | " + command.details + "\n"
      else:
        address = command.recipientObj.getAddress(command.specifier)
        if address:
          return addressString+" for "+name+":\n"+address
        else:
          return name + " has no " + addressString
    else:
      return "I know you want me to do something with addresses, but I don't know whose! (Yell at Daniel)\n"
    
  def do_addresses(self):
    for word in Events.ADDRESS_MODIFIERS:
      if findWord(self.specifier, self.leftString):
        self.specifier = word
        
  def handle_addresses(command):
    toRet = ""
    for user in command.group.users.getUsersSorted(lambda user: user.getName()):
      baseAddress = user.getAddress()
      if baseAddress:
        toRet += "Addresses for " + user.getName() + ":\n"
        toRet += "--" + baseAddress + "\n"
        for modifier in Events.ADDRESS_MODIFIERS: #Goes through all possible address types
          subAddress = user.getAddress(modifier)
          if subAddress:
            toRet += "--" + modifier.title() + ": " + subAddress + "\n"
    return toRet
    
  #do_joke objects will have a special ".jokeHandler" attribute
  #because spcifier can be an int, this also uses "details" if we have a variant of standard joke
  #Uses verbs: get, subscribe, unsubscribe
  def do_joke(self):
    self.verb = "get"
    if findWord(["types","kinds","categories"], self.leftString + " " + self.rightString): #If these are in either
      self.specifier = "type"
      return #Don't do anything else
    
    if findWord(["some", "a? ?few", "a? ?couple","several","many"], self.leftString):
      self.specifier = "some"
      
    match = re.search(r"\d+", self.leftString)
    if match:
      self.specifier = int(match.group())
      
    #Tries to get another type of joke, otherwise returns default
    jokeIdentifier = self.leftString.split(" ")[-1]
    self.jokeHandler = Jokes.getJokeType(jokeIdentifier) or Jokes.joke
    
    if self.jokeHandler == Jokes.joke:
      self.details = jokeIdentifier
      
    #Subscription fun!
    if findWord("subscribe", self.leftString):
      self.verb = "subscribe"
      self.setRecipient(self.leftString)
    elif findWord("unsubscribe", self.leftString):
      self.verb = "unsubscribe"
      self.setRecipient(self.leftString)
     
  def handle_joke(command):
    if command.verb == "get":
      if command.specifier == "type":
        return "Joke Types: " + " | ".join((joke + "s") for joke in Jokes.BaseJoke._jokeObjects if joke != "regular") #Join all the joke types in the dictionary
      else:
        toRet = ""
        numJokes = 1
        if command.specifier == "some":
          numJokes = random.randint(2,5) #Between 2 and 4
        elif type(command.specifier) == int:
          numJokes = min(max(1, command.specifier), 7) #Between 1 and 7
          
        if command.jokeHandler == Jokes.joke:
          for i in range(numJokes):
            toRet += Jokes.joke.getJoke(command.details) + "\n" #Add a joke to the buffer since it is just text. The details is possible category
        else:
          for i in range(numJokes):
            command.jokeHandler.postJoke(command.group) #Otherwise just post the jokes by themselves
            
        return toRet
    elif command.verb == "subscribe":
      if command.recipientObj:
        if command.jokeHandler.handleSubscribe(command.recipientObj, command.message):
          return "Subscribing '" + command.recipientObj.getName() + "' to " + command.jokeHandler.title+"s!"
        else:
          return "Could not subscribe '" + command.recipientObj.getName() + "' to " + command.jokeHandler.title+"s"
    elif command.verb == "unsubscribe":
      if command.recipientObj:
        ret = command.jokeHandler.handleUnsubscribe(command.recipientObj, command.message)
        if ret:
          return "'" + command.recipientObj.getName() + "' unsubscribed from " + command.jokeHandler.title + "s"
        elif ret == None:
          return "'" + command.recipientObj.getName() + "' was not subscribed to " + command.jokeHandler.title + "s in the first place..."
        else:
          return "'" + command.recipientObj.getName() + "' failed to unsubscribe from " + command.jokeHandler.title + "s"
          
      
  def do_name(self):
    filter = ["is", "was", "and"]
    self.details = filterWords(stripPunctuation(self.rightString), filter).strip()
    
    if findWord("real", self.leftString):
      self.specifier = "real"
    
    if findWord(["what is", "what are", "get"], self.leftString):
      self.verb = "get"
      if self.specifier != "real": #If they don't specifically want their real name, return all their names
        self.command = "names"
        return self.do_names()
    
    self.verb = "set"
    if findWord(["delete", "remove", "erase"], self.leftString):
      self.verb = "delete"
      self.details = self.rightString
      
    self.leftString = filterWords(self.leftString.replace("'s",""), filter) #Get rid of possessives
    self.setRecipient(self.leftString)
    
  def handle_name(command):
    if command.recipientObj:
      if command.verb == "set":
        if command.sender: #I am a spiteful webmaster
          if command.sender.ID in ["15748240"]:
            return "I'm sorry, " + command.sender.getName() + ", but you are disallowed from setting any names"
        
        if command.specifier == "real" or not command.recipientObj.realName:
          command.group.users.addRealName(command.recipientObj, command.details)
        else:
          command.group.users.addNewAlias(command.recipientObj, command.details)
        return "Added new name for " + command.recipientObj.getName(True) + ": " + command.details
      elif command.verb == "delete":
        return "Removing name for " + command.recipientObj.getName() + "... "
        try:
          index = int(command.details)
          try:
            toRemove = sorted(command.recipientObj.alias, key = str.lower)[index-1] #This relies on being the same sort as the one in "names"
          except IndexError:
            return "Could not remove name #"+str(index)+" (you only have "+str(len(command.recipientObj.alias))+ " names)"
          else:
            success = command.group.users.removeAlias(command.recipientObj, toRemove)
            if success:
              return "Successfully removed name '"+toRemove+"'"
            else:
              if toRemove == command.recipientObj.realName or toRemove == command.recipientObj.GMName:
                return "You cannot remove either your GroupMe Name or your set 'real' name"
              else:
                return "Could not remove name #"+str(toRemove) + ": " + toRemove + " (go yell at Daniel)"
        except ValueError:
          success = command.group.users.removeAlias(command.recipientObj, command.details)
          if success:
            return "Successfully removed name '"+command.details+"'"
          else:
            if toRemove == command.recipientObj.realName or toRemove == command.recipientObj.GMName:
                return "You cannot remove either your GroupMe Name or your set 'real' name"
            else:
              return "Could not find/remove name '"+command.details+"'"
      
    
  def do_names(self):  
    if findWord("purge all", self.leftString):
      self.verb = "purge"
      return #No more needs to be done
      
    self.verb = "get"
    if findWord("delete", self.leftString):
      self.verb = "delete"
      self.lefString = self.leftString.replace("delete", "")

      
    if findWord("all", self.leftString):
      self.specifier = "all"
    self.setRecipient(self.leftString)
    
  def handle_names(command):
    #META FUNCTION DEFINITION (used in two places below)
    def addAllNames(user):
      toRet = ""
      toRet += user.getName(preferGroupMe = True) + "\n"
      i = 1
      for name in sorted(user.alias, key = str.lower):
        toRet += str(i)+": " + user.specifyName(name) + "\n"
        i += 1
      return toRet
  
    if command.verb == "purge" and command.sender and command.sender.ID == "27094908": #Can only be accessed by me
      return "And botsly looked at what he had wrought, and deemed it evil"
      for user in command.group.users.userList:
        user.realName = None #Remove this
        for alias in user.alias.copy():
          command.group.users.removeAlias(user, alias)
      command.group.handler.write("PURGING ALL NAMES WITH HOLY FIRE", image = "http://i.groupme.com/1920x1080.png.8f8b5477e0c9438084b914eea59fb9f8.large")
 
    elif command.verb == "get":
      toRet = ""
      if command.specifier == "all": #If we want ALL names
        toRet += u"Printing out all names for everyone. \U0001f389 yay \U0001f389\n"
        for user in sorted(command.group.users.userList, key = lambda a: a.getName(preferGroupMe = True).lower()): #This part is copied from below. May want to refactor
          toRet += addAllNames(user)
      elif command.recipientObj:
        toRet += addAllNames(command.recipientObj)
      return toRet
    elif command.verb == "delete": #Implies that they want to delete all names
      if command.recipientObj:
        count = 0
        for name in command.recipientObj.alias.copy():
          count += int(command.group.users.removeAlias(command.recipientObj, name)) #Tries to remove all names, will fail for real and GM names
        return "Removed " + str(count) + " names for " + command.recipientObj.getName()
        
    
  def do_human_affection(self):
    log.command("Searching for human affection")
    self.recipientObj = self.group.users.getUser(self.leftString + " " + self.rightString)
    
  def handle_human_affection(command):
    toSend = command.sender
    if command.recipientObj:
      toSend = command.recipientObj
    if toSend:
      return "Love you " + toSend.getName() + u" \u2764"
    else:
      return u"Love you \u2764"
      
  def do_group_password(self): 
    if findWord(["whats?","get"], self.leftString + " " + self.rightString):
      self.verb = "get"
    else:
      self.verb = "set"
      self.details = filterWords(self.rightString, ["to","as"]).strip()
      
  def handle_group_password(self):
    if self.verb == "get":
      return "The website password is: " + self.group.getPassword()
    else:
      success = self.group.setPassword(self.details)
      return ("Successfully set website password to: " + self.group.getPassword()) if success else ("Could not set website password to '"+self.details+"'")
      
  def do_restart(self): pass
  def do_shutdown(self): pass
  
  def handle_restart(command):
    Events.NonBlockingRestartLock.acquire(blocking = False)
    log.command("SIGNALLING SERVER RESTART")
    return "Restarting Server!"
    
  def handle_shutdown(command):
    Events.NonBlockingShutdownLock.acquire(blocking = False)
    log.command("SIGNALLING SERVER SHUTDOWN")
    return "Shutting Down Server!"