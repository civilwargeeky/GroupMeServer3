#Handles all inbound and outbound communication, routes messages and data to appropriate modules
#Registers "Groups" that are the main GroupMe group that can be branched off of in tracked subgroups or event groups

#Note: A message takes the form:
""" {'created_at': 1436415083, 
     'name': 'Person',
     'avatar_url': 'http://i.groupme.com/640x640.jpeg.5c5ab9dae6374654a5afb5521953ba7e',
     'sender_id': '27152735',
     'group_id': '13972393',
     'system': False,
     'sender_type': 'user',
     'text': 'Message',
     'source_guid': '86FB9AB9-ACDD-47A1-A459-8887B79B8A47',
     'user_id': '27152735',
     'attachments': [],
     'id': '143641508393791778'} """

#Python Imports
import io
import json
import http.server
import socketserver #For the threading mixin
import traceback
from datetime import time, timedelta

#My Imports
import Commands
import Events
import Files
import Jokes
import Logging as log
import Network
import Groups
import Users
import Website

#Globals
SEND_ERRORS_OVER_GROUPME = not Events.IS_TESTING

class ServerStopError(Exception): #Just to let us know what has been done in messages
  def getValue(self):
    try:
      return self.args[0]
    except:
      return True

#This is mostly the same, but I want custom error logging
class Server(http.server.HTTPServer): 

  def __init__(self, *arg, **kwarg):
    super().__init__(*arg, **kwarg)
    self.exitValue = None #Defaults to not set

  def handle_error(self, request, client_address):
    Events.getLockObject().release() #Release the lock we have on message processing
    
    stringBuffer = io.StringIO()
    traceback.print_exc(file = stringBuffer)
    stringBuffer.seek(0) #Reset to start of message
    errorMessage = stringBuffer.read().replace("\n","\r\n")
    log.error("==== ERROR OCCURRED IN SERVER. PRINTING ERROR ====")
    log.error(errorMessage) #Output the message to logging
    
    if SEND_ERRORS_OVER_GROUPME:
      sendGroup = makeNamedGroup(99, "23222092", ("27094908", Files.getTokenList()[0]))
      sendGroup.setBot("3da109b71b8c3363c4b87a7e67")
      sendGroup.save()
      
      try:
        if sendGroup:
          log.network.statePush(False)
          success = sendGroup.handler.write("\nMESSAGE FOR YOU SIR:\n" + errorMessage)
          log.network.statePop()
          if success:
            log.error("Successful error report sent")
          else:
            log.error("Failed to send error report")
          
      except Exception as e: #I don't care about any errors here. jk
        raise e #Jk I do

  def finish_request(self, request, client_address):
    #Sets a lock object for the server. Updating groups/data in another thread will lock the server from responding to a request
    lock = Events.getLockObject()
    if lock:
      print("Acquiring lock for message processing") #Honestly I don't want to log this, but if I come look at the screen I would want to see this
      lock.acquire()
      print("Acquired lock")
      
    try:
      super().finish_request(request, client_address) #Actually processes the message
    except ConnectionAbortedError:
      log.net.debug("Of note: Connection Aborted")
    
    if not Events.NonBlockingShutdownLock.acquire(blocking = False):
      self.exitValue = False
      log.info.debug("Request indicates shutdown. Shutting down server")
      Events.quickDaemonThread(self.shutdown) #Because shutdown does a "wait" for the current request to end and causes deadlock
    Events.NonBlockingShutdownLock.release() #Release once checked
    
    if not Events.NonBlockingRestartLock.acquire(blocking = False):
      self.exitValue = True
      log.info.debug("Request indicates restart. Shutting down server")
      Events.quickDaemonThread(self.shutdown) #Because shutdown does a "wait" for the current request to end and causes deadlock
    Events.NonBlockingRestartLock.release() #Release once checked
    
    
    if lock:
      lock.release()
    

class ServerHandler(socketserver.ThreadingMixIn, http.server.BaseHTTPRequestHandler):
  def getContent(self):
    try:
      return self.rfile.read(int(self.headers.get('Content-Length'))).decode("UTF-8")
    except TypeError:
      return self.rfile.read().decode("UTF-8")

  def do_POST(self, messageOverride = None): #For GroupMe messages and server passwords
    if messageOverride:
      #Allow us to test without stealing the other server
      messageBody = messageOverride
    else:
      #Read all info from web response
      messageBody = self.getContent()
      
    try: #Block differentiating between groupMe responses and website messages
      message = json.loads(messageBody)
    except json.decoder.JSONDecodeError: #Failure is a website request and not a GroupMe request
      log.info.debug("Received a normal http POST message")
      self.body = messageBody #We actually need this...
      Website.handleRequest("POST", self) #Give web request with the message and headers
    else: #Success is for a groupMe message
      log.info.debug("Received GroupMe Message")
      ### Note: The way to implement headers is "send_response, send_header, send_header..., end_headers"
      ### Also: For writing body, just use self.wfile.write after end headers
      self.send_response(200) #Reply that we have received the message. No further response is needed
      self.end_headers()
      
      log.network.debug("Message received:", message)
      message = Commands.Message(message) #Give us all our nice functions
      #Group not existing can raise KeyError, terminating futher processing
      try:
        workingGroup = Groups.getGroup(message.group_id)
      except AttributeError:
        log.info.error("NO GROUP IN MESSAGE. MESSAGE: ", message)
      else: #There is a group in the message
        if workingGroup: #If the group exists
          log.info.debug("Handling message for Group",workingGroup.ID)
          workingGroup.handleMessage(message) #Yes, let us pass all the hard work to the helper files
        else:
          log.info.error("No group found associated with",message.group_id)
  

  def do_GET(self): #For web requests
    log.info.debug("Received a normal http GET message")
    try:
      Website.handleRequest("GET", self) #Give web request with the message and headers
    except Exception as e:
      self.send_response(500) #Internal server error
      self.end_headers()
      raise e #And GTFO
  
  #Log who the request was from
  def log_request(self, code="-",size="-"):
    pass
    
#Expects a tuple of (userID, token)
def makeNamedGroup(id, groupID, idTuple, initialPassword = None):
  if not Groups.getGroup(id):
    toRet = Groups.MainGroup(id, groupID)
    user = toRet.users.addUser(Users.User(toRet, idTuple[0])).setToken(idTuple[1])
    user.save()
  else:
    toRet = Groups.getGroup(id)
    
  #Regardless, set the password
  if initialPassword:
    toRet.setPassword(initialPassword)
  return toRet
  
def purgeGroups():
  for name in list(Groups.groupDict.keys()):
    Groups.groupDict[name].deleteSelf()
    
def main():

  """Initialize All Modules"""
  tokenList = Files.getTokenList() #[0] should be mine, and [1] should be my alt for group creation
  log.debug("Tokens:",tokenList)
  #Just my user id and token
  put = ("27094908", tokenList[0])
  
  #Totally Not The NSA Token
  Groups.Group.overlord = tokenList[1]
  
  #Just things
  log.network.debug.disable() #Suppress the return value of every message
  #log.command.low.enable() #For going through all the commands every time we get a command
  #log.user.low.enable() #For going through all the users every time we search for a user
  if Events.IS_TESTING:
    log.save.low.enable()
  
  #First load all the groups
  log.info("========== PRE-INIT (LOAD) ==========")
  toLoadList = []
  for folder in Files.getDirsInDir():
    if "Group " in folder: #If it a folder containing a group to load
      number = int(folder.split(" ")[-1])
      obj = (number, folder,) #Tuple of number and folder name
      flag = True
      for i in range(len(toLoadList)): #Sort the list
        if number < toLoadList[i][0]:
          toLoadList.insert(i, obj)
          flag = False
          break
      if flag: #If did not insert anywhere else
        toLoadList.append(obj)
        
  #Loadsd the groups guarenteed in order
  for group in toLoadList:
    Groups.loadGroup(group[1])
    
  log.info("Groups: ", Groups.getSortedList())
    
  #Do init and post-init
  log.info("========== INIT ==========")
  for group in list(Groups.getSortedList()): group.init()
  
  ### Named groups should be made after INIT to avoid duplicated initial users
  testGroup = makeNamedGroup(1, "23199161", put)
  
  toriGroup = makeNamedGroup(15, "23317842", put, "DLARulez")
  
  groupFam  = makeNamedGroup(2, "13972393", put, "easier")
  groupFam.setBot("cfe41d49a83d73874f4aa547b9")

  try: #This is so we can have our finally block remove any extra threads in case of error
    
    log.info("========== POST-INIT ==========")
    for group in list(Groups.getSortedList()): 
      try: group.postInit()
      except AssertionError: pass
    
        
    log.info("========== GROUP CLEANUP ==========")
    deletionList = Groups.getSortedList()
    deletionList.reverse()
    for i in deletionList.copy():
      if i.markedForDeletion:
        log.info("Deleting group", i)
        i.deleteSelf()
        del i
    del deletionList
    
  #try:
    def postEarlyMorningFact():
      joke = Jokes.funFacts.getJoke()
      if type(joke) == tuple:
        return Jokes.funFacts._postJoke(groupFam, ("Oh boy 3 A.M.!\n"+joke[0], joke[1]))
      return Jokes.funFacts._postJoke(groupFam, "Oh boy 3 A.M.!\n" + joke)
      
    def updateAllMsgLists():
      for searcher in MsgSearch._searcherList: #We could also probably get from all active groups instead of the searcher list
        searcher.GenerateCache()
    
    server = Server(('', Network.SERVER_CONNECTION_PORT), ServerHandler)
    
    #Update things for the groups every day at 5 a.m.
    log.info("Starting daily triggers")
    updaterDaily      = Events.DailyUpdater( time(5, 0), Groups.groupDailyDuties)
    updaterWebsite    = Events.DailyUpdater( time(4,58), Website.securityPurge) #Just do this seperately
    earlyMorningFacts = Events.DailyUpdater( time(3, 0), postEarlyMorningFact)
    monthlyMsgRefresh = Events.WeeklyUpdater(time(5,10), Events.WEEKDAY.SATURDAY, updateAllMsgLists, unitDifference = 4) #Once a month
    
    log.info("========== BEGINNING SERVER RECEIVING ==========")
    try:
      log.web("Starting server on port",Network.SERVER_CONNECTION_PORT)
      server.serve_forever()
    except KeyboardInterrupt:
      pass
      
    if server.exitValue != None: #Value of none means exited due to KeyboardInterrupt or something else
      log.info("Server shutting down from user input")
      if server.exitValue: #Exit value true means restart
        return 0;
      else: #False means shutdown
        raise AssertionError("Signal to main that we are done")
      
    #TESTING CODE:
    if Events.IS_TESTING:
      import traceback
      while True:
        print("> ", end = "")
        try:
          statement = input()
          if statement.lower() == "quit":
            break
          elif "=" in statement:
            exec(statement)
          else:
            print(eval(statement))
        except Exception as e:
          if isinstance(e, KeyboardInterrupt) or isinstance(e, EOFError):
            from os import _exit
            _exit(0) #Screw this crap, just get out of here. It's only for testing
          else:
            traceback.print_exc()
          
    raise AssertionError("Signal to main that we are done")
  #We need to kill all threads before exiting
  finally:
    Events.stopAllTimers()
    Events.SyncSave().saveAll(final = True)
  
    
if __name__ == "__main__":
  main()