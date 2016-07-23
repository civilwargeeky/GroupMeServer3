#A nice interface for Commands.
#A command should be passed an unadultered message and return a "Command" object that has nice functions to act on message data

import Groups #For type comparison
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
    
    
    
### Command Class ###
#In addition to message functions, this module will contain functions to respond to commands (and manipulate data that could be used in them)    
class Command():
  
  def __init__(self, group, message):
    if not isinstance(group, Groups.Group):
      raise TypeError(type(self).__name__ + " object expected a Groups.Group object, got " + str(type(group)))
    if not isinstance(group, Groups.Group):
      raise TypeError(type(self).__name__ + " object expected a Commands.Message object, got " + str(type(group)))
      
    self.group = group
    self.message = message
    
    #List of strings that will trigger commands
    self.triggerStrings = ['botsly', 'bot']
    
    self.init()
    
  #This is called during __init__, but can also be called whenever the text changes
  def init(self):
    #This will be assigned during initialization. You can have several commands per message, so like
    # "@botsly addresses @botsly my address is whatever" would just execute two separate commands
    # each element is a two-list consisting of "name match" (bot, botsly, etc.) and the "command" (rest of string)
    self.commandStrings = self.recurseFindCommand(self.message.text)
    
      
  #Recursively searches the string for trigger matches. Will start on right and work left, adding commands as it goes.
  #In the end, returns a list of two-lists of the form "name match" and "command"
  def recurseFindCommand(self, string, commandList = []):
    #log.debug("Entering recurse for",string)
    matchFound = False
    highestIndex = None
    #However, we need to ensure that we have the command at the closest to the start of the string possible, so it can be recursed
    for trigger in self.triggerStrings:
      #log.debug("Testing",trigger)
      index = string.lower().rfind("@"+trigger+" ")
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
  
