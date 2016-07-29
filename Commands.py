#A nice interface for Commands.
#A command should be passed an unadultered message and return a "Command" object that has nice functions to act on message data

import re

import Groups #For type comparison
import Jokes  #For joke object getting
import Logging as log

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
    for trigger in sorted(self.triggerStrings, key = len):
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
   
### Command Utiltites ###
def filterWords(string, wordList):
  for word in wordList:
    string = re.sub(r"\b"+word+r"\b", "", string, re.I)
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
"""
class Command():

  #If sender is set, it should be a User object that is the default user for an action. Set if action detects "me" or similar
  def __init__(self, group, commandString, botString, sender = None):
    if not isinstance(group, Groups.Group):
      raise TypeError(type(self).__name__ + " object expected a Groups.Group object, got " + str(type(group)))
      
    self.commands = {name: None for name in [\
                     "help", "address", "addresses", "joke", "name" \
                     ]}
    #Example: {"residence":"address"}
    self.commands.update({"jokes":"joke", r"facts?":"joke", r"pics?":"joke", "pictures?":"joke",
                          "called":"name"})
    
    self.group = group
    self.message = commandString
    self.bot = botString
    self.sender = sender
    
    #Things to be set by a command function
    self.verb         = None
    self.recipient    = None
    self.recipientObj = None #This will be a user object from a userlist
    self.specifier    = None
    self.command      = None #This is not set by the called function
    self.details      = None
    #Thsee are for left and right of command
    self.leftString   = None
    self.rightString  = None
    
    log.command.low("Command String:",self.message)
    for command in self.commands:
      log.command.low("Looking for command:", command)
      match = findWord(command, self.message)
      if match:
        methodName = "do_"+(self.commands[command] or command)
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
  
  def do_help(self):
    return
  
  addressModifiers = ["college"]
  
  def do_address(self):
    self.details = filterWords(stripPunctuation(self.rightString), ["in","is", "to"]).strip()
    
    remainingString = self.leftString.strip()
    if findWord("is", self.rightString):
      self.verb = "set"
    for word in ["set", "get", "what'?s?","where'?s?"]:
      match = re.search(r"\A"+word+r"\b", remainingString, re.I)
      if match:
        self.verb = "set" if word is "set" else "get" #Let them know for sure what it is
        remainingString = remainingString[match.end():].lstrip() #Take out the word we found
        break
    
    for word in self.addressModifiers:
      match = re.search(r"\b"+word+r"\Z", self.leftString.rstrip(), re.I)
      if match:
        self.specifier = word
        remainingString = remainingString[:match.start()].rstrip()
        break
        
    remainingString = remainingString.strip()
    self.setRecipient(remainingString)
    
  def do_addresses(self):
    for word in self.addressModifiers:
      if findWord(self.specifier, self.leftString):
        self.specifier = word
    
  #do_joke objects will have a special ".jokeHandler" attribute
  #because spcifier can be an int, this also uses "details" if we have a variant of standard joke
  def do_joke(self):
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
      
  def do_name(self):
    filter = ["is", "was"]
    self.details = filterWords(stripPunctuation(self.rightString), filter).strip()
    self.leftString = filterWords(self.leftString.replace("'s",""), filter) #Get rid of possessives
    self.setRecipient(self.leftString)