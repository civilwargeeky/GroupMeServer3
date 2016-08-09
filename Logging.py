#Standard logging interface with several levels. Log is tied to file system.

import datetime

import Files

_fileName = "log"

class BaseLogger():
  maxSize = 0

  def __init__(self, tag, tagPrefix, enabled = True, writeToFile = True):
    self.tag = (tagPrefix + " " + tag).lstrip()
    self.enabled = enabled
    self.writeToFile = writeToFile
    #The stateStack works so you can temporarily set state as much as you want, and corresponding calls to pop from the stack will revert
    #the logger to its original state
    self.stateStack = []
    self.linked = True #Always linked to a parent by default
    
    if len(self.tag) > BaseLogger.maxSize:
      #print("Tag: {: 2}".format(len(self.tag)), self.tag)
      BaseLogger.maxSize = len(self.tag)
  
        
  def setState(self, toSet): self.enabled = toSet
  ### SHOULD NOT BE USED INTERNALLY - Unlinks from parent ###
  def enable(self):  
    self.setState(True)
    self.linked = False #If set externally, assume this isn't linked
  def disable(self): 
    self.setState(False)
    self.linked = False
  on = enable
  off = disable
  
  def statePush(self, state):
    self.stateStack.append(self.enabled)
    self.setState(state)
  
  def statePop(self):
    self.setState(self.stateStack.pop())
    
  #Because one way follows an old convention I have, and the other is common sense
  #And I got frustrated
  pushState = statePush
  popState  = statePop
  
  @staticmethod
  def logPrint(*arg, **kwarg):
    try:
      print(*arg, **kwarg)
    except UnicodeEncodeError:
      print("Unable to print unsupported chars")
    except Exception as e:
      pass
      
  @staticmethod
  def log(*arg):
    with Files.LogAccessor(_fileName) as file:
      #First print out a timestamp
      file.write(datetime.datetime.now().strftime("%y-%m-%d %H:%M:%S").encode("unicode_escape"))
      file.write(b": ")
      for item in arg:
        if type(item) == str:
          file.write(item.encode("unicode_escape"))
        else:
          file.write(repr(item).encode("unicode_escape"))
        file.write(b" ")
      file.write(b"\r\n")
  
  def write(self, *arg, **kwarg):
    if self.enabled:
      if "tag" in kwarg:
        tag = kwarg["tag"] + " " + tag
      prefixString = "{:<{maxSize}}:".format((self.tag).lstrip().upper(), maxSize = BaseLogger.maxSize)
      #prefixString = datetime.datetime.now().strftime("%y-%m-%d %H:%M:%S") + " " + prefixString
      self.logPrint(prefixString, *arg)
      if self.writeToFile: self.log(prefixString, *arg)
  
  def __call__(self, *arg, **kwarg):
    return self.write(*arg, **kwarg)
      
class Logger(BaseLogger):
  def __init__(self, tag, enabled = True, writeToFile = True, defaultTag = "DBG"):
      self.enabled = enabled
      self.writeToFile = writeToFile
      self.stateStack = []
      self.modules = []
      
      self.addModule("debug", BaseLogger(tag, "DBG", enabled, writeToFile), link = True)
      self.addModule("error", BaseLogger(tag, "ERR", enabled, writeToFile), link = True)
      self.addModule("web"  , BaseLogger(tag, "WEB", enabled, writeToFile), link = True)
      self.addModule("low"  , BaseLogger(tag, "LOW", False, writeToFile)  , link = False) #Low is diabled by default
      
      self.tag = (defaultTag[:3] + " " + tag).lstrip()
      
      if len(self.tag) > BaseLogger.maxSize:
        #print("Tag: {: 2}".format(len(self.tag)), self.tag)
        BaseLogger.maxSize = len(self.tag)
    
  def addModule(self, name, obj, link = True):
    obj.linked = link #If an object is "linked" it will be toggled with a setState
    setattr(self, name, obj) #Set say "self.error = BaseLogger(tag, "ERR")"
    self.modules.append(obj)
    
  def setState(self, state):
    super().setState(state)
    for module in self.modules:
      if module.linked:
        module.setState(state)
    
      
      
#Now we make objects to be used by various other modules
main      = Logger("INFO", defaultTag = "") #Notification of the main functions of the server. Like "Starting" "Receiving Message" "Handling Web Request"
info      = main
debug     = Logger("NRM") #Debug messages (should not be necessary to determine function of server)
extra     = Logger("XTRA") #Debug about things that make lots of writes and are not necessary

#Per module
group     = Logger("GROUP") #Debug for the "Groups" module
user      = Logger("USER") #Debug for the "Users" module
event     = Logger("EVENT") #Debug for the "Events" module relating to threading and when an update will be called
network   = Logger("NET") #Debug for io with internet (what is going on with networking module)
net   = network
command   = Logger("CMD") #Debug for commands
file      = Logger("FS") #Debugging relating to reading and writing files
security  = Logger("SEC") #Information about authentification and such
joke      = Logger("JOKE") #Information about the "Jokes" module
analytics = Logger("RECORD") #Logging info relating to analytics and loggin (messages per day whatever)

#Other
save      = Logger("SAVE") #Debugging related to saving and loading files
error     = Logger("ERROR", defaultTag = "") #Information of errors that are not server-stopping, but bad
unsafe    = Logger("SELF", writeToFile = False) #For debugging the debugging process