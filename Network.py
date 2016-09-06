#A network interface to process certain functions related to the groupMe website
#Can create new bots, make new groups, etc.
#Many functions will require a "BotMaster" user from "Users.py" to do tasks. For some tasks, a "Bot" will be sufficient (each Bot/Botmaster is tied to a Group already)

import datetime
import json
import http.client
import socket #For error handling
import time
import uuid #For poster message sending
from urllib.parse import urlencode

import Files
import Groups
import Logging as log
import Users

IP_ADDRESS = None #Will be set when we need a bot, and can be reset
SERVER_CONNECTION_PORT = 7502
IP_UPDATE_TIME         = 60*60*2 #2 Hours between checks
_lastIPUpdateTime = 0

#This is an object so that I can use "Response.code" and then just have the return object be a dict
class Response(dict):
  def setCode(self, code):
    self.code = code
    return self

#You are meant to make a connection object to a website, and then you can make as many requests as you want from it. Connections will be opened and closed automatically.
class Connection():
  debugCutoffLength = 1000
  messageSplitTime  = 0.25

  #Opens a connection to the target website.
  def __init__(self, target = "api.groupme.com", https = False, encoding = "utf-8"):
    self.target = target
    self.https = https
    self.encoding = encoding
    self.lastRequest = 0
      
  #This sends a messasge to an external website
  #If not forceLog, truncates long responses
  def message(self, method, extension = "", query = {}, headers = {}, body = None, timeout = None, forceLog = True):
    #Only checks for sleep if we have sent at least one message
    currTime = time.time() #So we don't have any time resolution issues
    if self.lastRequest and (currTime-self.lastRequest < self.messageSplitTime):
      time_ = self.messageSplitTime - (currTime-self.lastRequest)
      log.network.debug("Too many messages, waiting", time_)
      time.sleep(time_)
    queryString = ""
    if self.https: #Initialize an HTTP connection object
      handle = http.client.HTTPSConnection(self.target, timeout = timeout)
    else: 
      handle = http.client.HTTPConnection(self.target, timeout = timeout)
    if len(extension) > 0 and extension[0] != "/": extension = "/"+extension
    log.network("Starting", method, "request to", self.target+extension)
    if query: 
      queryString = "?" + urlencode(query, safe=":")
      log.network.low("Query:", queryString)
    if headers: log.network.debug("Headers:", headers)
    if body: log.network.debug("Body:", body)
    try:
      handle.request(method, extension+queryString, body = (body.encode(self.encoding) if body else None), headers = headers)
      self.lastRequest = time.time() #Set the time when we finished the last request
    except socket.gaierror:
      log.network.error("Wow. The internet is down. Well that's a problem")
      raise ConnectionError("Internet Down. Please Check Connection")
      
    response = handle.getresponse()
    data, code = response.read().decode("utf-8"), response.getcode()
    log.network("Response Code:", code)
    log.network.debug("Message:", data if len(data) < self.debugCutoffLength or forceLog else (data[:1000] + "..."))
    handle.close()
    return data, code
  
  def get(self, url = "", query = {}, headers = {}, body = None, timeout = None, forceLog = True): return self.message("GET", url, query, headers, body, forceLog)
  def post(self, url = "", query = {}, headers = {}, body = None, timeout = None, forceLog = True): return self.message("POST", url, query, headers, body, forceLog)
  
IP_HANDLER_1 = Connection("wtfismyip.com") #Object to get the current IP address
IP_HANDLER_2 = Connection("icanhazip.com") #For later, mess with timeouts and things so that we can try from different places
def getIPAddress():
  global _lastIPUpdateTime, IP_ADDRESS
  if time.time() - _lastIPUpdateTime > IP_UPDATE_TIME: #If updated in last six hours
    ip, code = None, None
    try:
      ip, code = IP_HANDLER_1.get("text", timeout = 5)
    except socket.timeout:
      try:
        ip, code = IP_HANDLER_2.get("", timeout = 5)
      except socket.timeout:
        log.net.error("FAILED TO ACQUIRE IP ADDRESS FROM WEB!")
    if code == 200:
      IP_ADDRESS = "http://"+ip.rstrip()+":"+str(SERVER_CONNECTION_PORT)
      _lastIPUpdateTime = time.time()
      return IP_ADDRESS
      
    #If we can't get the ip address, we cannot make new bots, which is bad
    raise RuntimeError("Could not obtain IP address. Process returned code " + str(code))
  #If ip has been updated recently
  return IP_ADDRESS
  
#Returns whether or not the server's ip has changed since the last time we checked (instance-to-instance)
def hasIPChanged():
  global IP_ADDRESS
  
  _ipFile = Files.getFileName("ip_address")

  #Get the last ip we had
  oldIP = IP_ADDRESS
  if not oldIP:
    try:
      with open(_ipFile) as file:
        oldIP = file.read().rstrip()
    except FileNotFoundError:
      log.info.debug("No ip file")
  
  #Get our new ip, then save it
  newIP = getIPAddress()
  if oldIP != newIP: #Only need to write if we changed anything
    with open(_ipFile, "w") as file:
      file.write(newIP)
    
  if oldIP == None: return False #This means we haven't checked before, so the ip can't be differentiating
  return oldIP != newIP
    
  
class GroupMeHandler():
  def __init__(self, group):
    self.group = group #Group reference
    self.connection = Connection(https = True) #No params because the default is "api.groupMe.com"
    
    self.poster = None
    self.bot    = None
    
  def postInit(self):
    #pass #I think we should only need to get the poster and bot when we actually need to post or get something
    self.poster = self.group.getBotMaster() #Get the botmaster's token
    self.bot    = self.group.getBot() #Get bot token
    
  def getPoster(self):
    if not self.poster: self.poster = self.group.getBotMaster()
    return self.poster
    
  def getBot(self):
    if not self.bot: self.bot = self.group.getBot()
    return self.bot
    
  def getBotFromWeb(self):
    response = self.get("bots")
    if response.code == 200:
      for groupData in response.values():
        if groupData['group_id'] == self.group.groupID:
          return groupData['bot_id']
    else:
      log.net.error("Could not get bots list from web, code",response.code)
      return False
    
  def message(self, method, url, query = {}, headers = {}, body = {}, addToken = True):
    if not self.getPoster():
      raise RuntimeError("ERROR: GroupMeHandler has no BotMaster from group " + str(self.group.ID))
      return None
      
    if addToken:
      query["token"] = self.getPoster() #Add in the token to all GroupMe communcations
    #Dump in the body as well
    response, code = self.connection.message(method, "/v3/" + url, query, headers, json.dumps(body) if body else None)
    if type(response) == str and "{" in response[:5]: #Things like deleting groups does not return a response, just a code
      data = json.loads(response)
      if 'meta' in data and code >= 400:
        log.network("Meta:",data['meta'])
      if not 'response' in data:
        return Response().setCode(code)
      data = data['response'] or {}
      if type(data) == list:
        data = {i : data[i] for i in range(len(data))}
      return Response(data).setCode(code) #Or {} because sometimes the response exists, but is NULL
    else:
      return Response().setCode(code)
    
  def get(self, url, query = {}, headers = {}, body = None, addToken = True): return self.message("GET", url, query, headers, body, addToken)
  def post(self, url, query = {}, headers = {}, body = None, addToken = True): return self.message("POST", url, query, headers, body, addToken)
  
  def getGroupData(self, extension = "", query = {}, headers = {}, body = None):
    return self.get("/".join(["groups",self.group.groupID,extension]), query, headers, body)
    
  ### Group I/O Functions ###
  def _write(self, message, image = None, attemptRectify = True): #This method is for messages guarenteed to be less than 1000 characters in length
    log.net.low("Bot writing message:", message)
    bot = self.getBot()
    if not bot:
      raise RuntimeError("Group " + str(self.group.ID) + " could not acquire a bot for message writing")
    response = self.post("bots/post", body = {"text":str(message), "bot_id":bot, "attachments":([] if not image else [{"type":"image","url":image}])}, addToken = False)
    if response.code == 202:
      log.net("Message write successful")
      return True
    elif response.code == 404 and attemptRectify:
      log.net.error("Message write failed. Probable bot ID mismatch. Fixing")
      if self.rectifyBot():
        return self._write(message, image, attemptRectify = False) #We only want to attempt to rectify once
      else:
        log.net.error("Rectification attempt failed. Cannot post message")
        return False
    else:
      log.net.error("MESSAGE WRITE FAILED:",response.code)
      return False
      
  def _writePoster(self, message, image = None):
    log.net.low("Human writing message:", message)
    poster = self.getPoster()
    if not poster:
      raise RuntimeError("Group " + str(self.group.ID) + " could not acquire a poster for message writing")
    response = self.post("groups/"+self.group.groupID+"/messages", headers = {"Content-Type":"application/json"}, body = {"message": {"source_guid": str(uuid.uuid4()), "text":str(message), "attachments":(None if not image else [{"type":"image","url":image}])}})
    if response.code == 201:
      log.net("Message write successful")
      return True
    else:
      log.net.error("MESSAGE WRITE FAILED:",response.code)
      return False
  
  def write(self, message, image = None, fromPoster = False):
    function = self._writePoster if fromPoster else self._write
    if not log.net.low.enabled: #Don't want to print the same message twice here
      log.net("Human" if fromPoster else "Bot", "writing message:", message)
    while len(message) >= 1000: #There is a limit on the length of messages we can write
      end = message.rfind("\n", 600, 999) #See if we can find an enter, split there
      if end < 0:
        end = message.rfind(" ", 0, 999) #Is there at least a space somewhere?
        if end < 0: end = 999 #Screw it
      function(message[0:end])
      message = message[end+1:]
    return function(message, image)
    
  def writePoster(self, message, image = None):
    return self.write(message, image = image, fromPoster = True)
    
  ### Group Management Functions ###
    
  def createGroup(self, groupName, imageUrl = None):
    return self.post("groups", body = {"name" : groupName, "imageUrl" : imageUrl})
    
  def deleteGroup(self, groupID):
    return self.post("/".join(["groups", groupID, "destroy"]))
    
  def updateGroup(self, name = None, description = None, image = None):
    updateDict = {}
    if type(name) == str: updateDict.update({"name":name})
    if type(description) == str: updateDict.update({"description":description})
    if type(image) == str: updateDict.update({"image_url":image})
    return self.post("/".join(["groups", self.group.groupID, "update"]), body = updateDict)
    
  def changePosterName(self, newName):
    return self.post("/".join(["groups", self.group.groupID, "memberships","update"]), body = {"membership": {"nickname":newName}})
    
  def addUsers(self, userList):
    if type(userList) != list:
      raise TypeError("addMembers expects 'list', got "+ str(type(userList)))
    for user in userList:
      if not isinstance(user, Users.User) or not (user.GMName or user.realName):
        raise TypeError("in addMembers: not all users to add were of type 'User' or had a name")
      
    return self.post("/".join(["groups",self.group.groupID,"members","add"]), body = {"members": [{"nickname":(person.GMName or person.realName),"user_id":person.ID} for person in userList]})
    
  def removeUser(self, user):
    log.network("Attempting to remove user",user)
    #Get all current member data. Looking for "membership ids"
    log.network("(Next web call is getting 'membership_id')")
    groupData = self.get("groups/"+self.group.groupID)
    if groupData.code == 200:
      for data in groupData['members']:
        if data['user_id'] == user.ID:
          #Remove the user using their "membership id" which is not the same as their user id
          success = self.post("/".join(["groups",self.group.groupID,"members",data['id'],"remove"]))
          if success.code == 200:
            log.network("Removal success")
            return True
          else:
            log.network("Removal failure. Code:",success.code)
            return False
    log.network("Could not remove user")
    return False

  ### Bot Management Functions ###
  
  #Returns the list of bots associated with the group's botmaster
  def getBotData(self):
    response = self.get("bots")
    if response.code == 200:
      log.net.debug("Downloaded data for",len(response),"bots")
      return [i for i in response.values()] #Because it returns a wierd dict of {0:{dictValue}, 1:{dictValue}...}
    log.net.error("Failed to download bot data for", self.group)
    return False
  
  def createBot(self, name, avatar = None, mainBot = True):
    log.net("Making a new bot for Group",self.group.ID)
    postBody = {"bot":{"name":name, "group_id":self.group.groupID}}
    if avatar:
      #Check if the picture is properly uploaded
      if "i.groupme.com" in avatar:
        #Checks a tuple to see if it has the proper start. If it doesn't, append it
        if not avatar.startswith(("http://","https://")):
          avatar = "http://"+avatar
      else:
        log.group.error("NOTE: Bot has an invalid Avatar Url! Picture will not show up as intended")
      postBody['bot']['avatar_url'] = avatar
    if mainBot:
      postBody['bot']['callback_url'] = getIPAddress()
    else:
      postBody['bot']['callback_url'] = "http://127.0.0.0"
    response = self.post("bots", body = postBody)
    if response.code == 201:
      log.net("Bot create successful")
      return response['bot']['bot_id']
    log.net.error("Bot create failed")
    return False
    
  def deleteBot(self, botID): #Note: Bots are deleted when their group is deleted. No need to delete them manually
    log.net("Destroying bot for Group",self.group.ID)
    response = self.post("bots/destroy", query = {"bot_id": botID})
    return response.code == 200
    
  def createBotsly(self):
    success = self.createBot("Botsly McBottsworth", "http://i.groupme.com/300x300.jpeg.a49a6f825b5c4e1b885308005722b4f3")
    if success: return success #If we just created a new botsly
    #Otherwise, it is likely false due to 400 (already exists error), and we will attempt to rectify
    return self.rectifyBot(saveData = False) #If our bot was created but not returned (known issue), check to see if it actually exists
    
  #This function will attempt to reset the group's bot to the proper bot id
  #if saveData is False, will return the bot_id on success instead of just True
  def rectifyBot(self, botData = None, saveData = True):
    log.net("Attempting to rectify main bot of",self.group)
    botInfo = botData or self.getBotData() #will use given data if it exists
    if botInfo:
      for bot in botInfo:
        #If the bot is the proper full bot for our group
        if bot['group_id'] == self.group.groupID and bot['callback_url'] == getIPAddress():
          log.net("Rectify success")
          if saveData:
            self.bot = bot['bot_id']
            self.group.bot = bot['bot_id']
            self.group.save()
            return True
          else:
            return bot['bot_id']
    else:
      log.net("Rectify failure")
      return False
    
  #WARNING: UNTIL A BOTS CLASS IS MADE, THIS WILL ONLY REMAKE BOTSLYS
  def updateBots(self, botsList):
    if type(botsList) == str:
      botsList = [botsList]
      
    for bot in botsList[:1]: #...only doing the first one for now
      log.net("Updating bot with ID",bot)
      if self.deleteBot(bot):
        log.net("Successfully deleted bot! (sleeping for them to update database)")
        time.sleep(3) #Arbitrary time, should be more than enough
        id = self.createBotsly()
        if id:
          self.bot = id #Update us
          self.group.bot = id #Update our parent group
          self.group.save()
        else:
          log.net.error("COULD NOT UPDATE BOT ON CREATE, ERRORING")
          raise RuntimeError("COULD NOT CREATE BOT FOR UPDATE")
      else:
        log.net.error("COULD NOT UPDATE BOT, ERRORING")
        raise RuntimeError("COULD NOT DELETE BOT FOR UPDATE")
        
  ### Group Info/Utility Functions ###
  
  def getUsers(self):
    groupData = self.get("groups/"+self.group.groupID)
    if groupData.code == 200:
      return groupData['members']
    return False
  
  def getEvents(self):
    response = self.get("conversations/"+self.group.groupID+"/events/list", query = {"end_at":datetime.datetime.today().replace(microsecond=0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))).isoformat()})
    if response.code == 200:
      #Check if any events were deleted. We don't want them
      for event in range(len(response['events'])-1,-1, -1): #Go through the list backwards, deleting items as we go
        if 'deleted_at' in response['events'][event]:
          response['events'].pop(event) #Remove event from list of events
          
      return response['events']
    log.net.error("Failed to get events for group",self.group.ID,"code:",response.code)
    return list()
  
  #Returns detailed event data on an event
  def getEventData(self, eventID):
    events = self.getEvents()
    for event in events:
      if event['event_id'] == eventID:
        return event
    return False
    