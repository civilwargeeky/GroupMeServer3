#This file handles all the jokes and bat facts and other misceallaneous stuff that goes on in the server.

import xml.etree.ElementTree as xml
import copy, json, random, html.parser, re

import Events
import Files
import Logging as log
import Network

defaultDefaultJoke = "Could not get a fact"

#Post jokes that the user is subscribed to
def postReleventJokes(user, text):
  for title in BaseJoke._jokeObjects:
    try:
      if user.data[BaseJoke._dictString][title]: #If the user is subscribed to this
        if BaseJoke._jokeObjects[title].postSubscription(user, text): #Post the joke for this user
          log.joke.debug("Posted subscription joke of type", title) #Log whether joke was actually posted or not
        else:
          log.joke.debug("Did not post subscription joke of type", title)
    except KeyError:
      pass
    
postReleventFacts = postReleventJokes

#BaseJoke just acts an interface, describing what methods jokse should have
class BaseJoke():

  #String to access in the user's "data" attribute
  _dictString = "Jokes"
  #Dict of "title": objReference
  _jokeObjects = {}
  
  def __repr__(self):
    return "<Jokes."+str(type(self))+" object with title '"+self.title+"'>"
  
  ### ALL SUBCLASSES OF JOKE MUST CALL super() TO ADD THEM TO THE LIST ###
  def __init__(self, title):
    #Title should be a human-readable name for the joke object
    self.title = title
    self._jokeObjects[title] = self
    
  #A function to get more jokes (like from the internet from a file)
  def acquireJokes(self):
    pass
    
  #A function that should return the string of a joke
  #Typically used internally
  #PRE : Should be given a group so can acquire from the internet
  #POST: Should return a string. If there is only a joke, should return string. If joke and picture url, should return a 2-tuple of jokeString and urlString. If joke get failed, should return False
  def getJoke(self):
    return ""
    
  getFact = getJoke #Alias
    
  #A function that should return the url of a picture to go along with the joke
  #This should usually return the url of some generic image, as it is called in postJoke if no picture is found
  #Typically used internally
  def getPicture(self):
    return None
    
  #Just handles the switching for tuple/regular
  def _postJoke(self, group, joke, fromPoster = False):
    if type(joke) == tuple:
      return group.handler.write(*joke, fromPoster = fromPoster)
    elif type(joke) == str:
      return group.handler.write(joke, self.getPicture(), fromPoster = fromPoster)
    else:
      log.joke.error("GET JOKE DID NOT GET JOKE", "Cannot Post Joke/Fact")
    
  #Posts a joke to the group
  #PRE : group should be the group to post to, *arg is passed to getJoke
  #POST: Returns True if a message was posted to the user's group, False otherwise
  def postJoke(self, group, *arg):
    joke = self.getJoke(*arg)
    return self._postJoke(group, joke)
  
  postFact = postJoke #Alias
    
  #Posts a joke in response to a subscriber message
  #PRE : user is the user who posted (in the group), text is the text of the message the user had sent
  def postSubscription(self, user, text):
    return self.postJoke(user.group)
    
  #Handles changing some sort of data so that the given user is subscribed to fact. When that user sends a message, postSubscription will be called with the text of their post
  #PRE : user is the User that posted the message, text is the text of the message the user sent
  #POST: Returns True if user subscribed, False otherwise
  def handleSubscribe(self, user, text):
    if self._dictString not in user.data:
      user.data[self._dictString] = {}
    user.data[self._dictString][self.title] = True
    user.save()
    return True
  
  #PRE : user is the User that posted the message, text is the text of the message the user sent
  #POST: Returns True if user was unsubscribed, False if not allowed to unsubscribe, and None if not subscribed in the first place
  def handleUnsubscribe(self, user, text):
    try:
      if not user.data[self._dictString][self.title]:
        return None #If we weren't subscribed already
      del user.data[self._dictString][self.title]
      user.save()
      return True
    except KeyError: #If we get KeyError, this joke was never set in the first place
      pass
    
  #Checks if the user has been subscribed to the given joke channel
  def isSubscribed(self, user):
    try:
      return user.data[self._dictString][self.title]
    except KeyError: #If KeyError, joke was never set for this person
      return False

class JokeWebsiteParser(html.parser.HTMLParser):
  def __init__(self):
    super().__init__()
    self.careData = self.careTags = False
    self.careAtAll = True
    self.joke = ""
  def handle_starttag(self, tag, attrs):
    if not self.careTags:
      if self.careAtAll:
        if tag == "p" and len(attrs) > 0 and attrs[0][1] == "right": self.careTags = True #All p tags after this are the joke
    else:
      if tag == "div":  self.careTags = self.careAtAll = False #The end of the joke
      if tag == "p": self.careData = True #The start of the joke
  def handle_data(self, data):
    if self.careData and self.careAtAll:
      self.joke += data.strip()+"\n"

#Standard Joke is the OG internet joke, is a singleton, and this handler existed a LONG time
class StandardJoke(BaseJoke):
  def __init__(self):
    super().__init__("regular")
    self.categories = ["haha","signs","nerd","professional","quotes","lightbulb","blonde","laws"]
    self.connection = Network.Connection("www.randomjoke.com")
    
  def getJoke(self, category = ""):
    log.joke.debug("New Joke, received category",category)
    if category and type(category) != str:
      raise TypeError("getJoke expected a str category, got " + str(type(category)))
      
    category = category.lower()
    if not category in self.categories: category = random.choice(self.categories)
    try:
      log.network.low("Suppressing network for joke acquisition")
      log.network.debug.pushState(False) #Super long, super annoying message
      joke, code = self.connection.get("/topic/"+category+".php")
      log.network.debug.popState()
      joker = JokeWebsiteParser()
      #This is for debugging
      #file = open("lastJoke.html","wb")
      #file.write(joke)
      #file.close()
      joker.feed(joke)
      joker.close()
    except (UnicodeDecodeError): joker.joke = "I don't get it D: (The joke website is acting up)"
    return "A joke from the '"+category.title()+"' category!\n" + (re.sub(r"[\n\r]"," ",joker.joke).strip() if len(joker.joke) < 1000 else "JK the joke is about English Class because its so long and drawn out") + "\n" 

    
#Simple jokes simply return jokes stored in a list or tuple
class SimpleJoke(BaseJoke):

  def __init__(self, title, defaultJoke = defaultDefaultJoke):
    super().__init__(title)
    self.defaultJoke = defaultJoke
    self.jokes       = []
    
    self._chosen = [] #We can try and not to return the same joke multiple times
    
  def setJokes(self, jokesList):
    self.jokes = list(jokesList)
    self._chosen.clear()
    
  def getJoke(self):
    if len(self.jokes) > 0:
      #Pick a joke that hasn't been picked recently
      choice = random.choice([i for i in range(len(self.jokes)) if i not in self._chosen])
      self._chosen.append(choice) #Add the joke to the blacklist
      #If we have gone through at least 3/4 of the jokes, start removing jokes from the blacklist
      if len(self._chosen) > (len(self.jokes) * 3 // 4):
        self._chosen.pop(0) #Will only fire if at least one element in list. No Error.
        
      return self.jokes[choice]
    #If we have no jokes, return the default one
    return self.defaultJoke
    
  def postAllJokes(self, group):
    log.joke("Posting all",self.title," jokes")
    jokeCopy = copy.copy(self.jokes)
    random.shuffle(jokeCopy)
    counter = 0
    for joke in jokeCopy:
      counter += int(self._postJoke(group, joke))
    log.joke("Posted",counter,"/",len(jokeCopy),"jokes")
    
    
#SimpleFileJokes are just SimpleJokes that can save their data and load it as json from a file
class SimpleFileJoke(SimpleJoke):
  def __init__(self, title, defaultJoke = defaultDefaultJoke):
    super().__init__(title, defaultJoke)
    self.isLoaded = False
    self.fileName = Files.getFileName(self.title.replace(" ",""), prefix = "LOGFACT_")
    
  def setJokes(self, jokesList):
    super().setJokes(jokesList)
    self.save()
    
  def save(self):
    log.file.debug("Saving jokes file",self.fileName)
    with open(self.fileName, "w") as file:
      json.dump(self.jokes, file)
      
  def load(self):
    if not self.isLoaded:
      log.file.debug(self.title,"has not loaded, loading")
      try: 
        with open(self.fileName) as file:
          tempJokes = json.load(file)
          self.jokes = []
          for joke in tempJokes:
            if type(joke) == list:
              self.jokes.append(tuple(joke))
            else:
              self.jokes.append(joke)
        self.isLoaded = True
              
      except (FileNotFoundError, json.JSONDecodeError):
        log.file.error("Joke file read failed")
    
  def getJoke(self):
    #First load to see if we have any files to get
    self.load()
    
    return super().getJoke()
    
#Inherits everything from SimpleJoke, just has an extra method that's added to getJoke
class SimpleFact(SimpleJoke):
  def __init__(self, title, defaultJoke = defaultDefaultJoke):
    super().__init__(title, defaultJoke)
    #If these are pics instead of facts
    if title.lower().split()[1] == 'pic': #Strip any numbers (Corgi Pic 1)
      self.setFactString("PICS")
    

  def setFactString(self, string):
    self.factString = string[:4].upper()

  #We want to try and turn "Turtle Facts" from "TUR" into "TRT" or something like that.
  def makeMessageFun(self, string):
    #Just try and remove a vowel if its too long
    phoneGroup = self.title.split(" ",1)[0].lower()
    if len(phoneGroup) > 3:
      for c in ['a','e','i','o','u']:
        phoneGroup = phoneGroup.replace(c, "", 1)
        if len(phoneGroup) <= 3: break
    
    #Post with fun message and phone number
    #NOTE: Unsubscribe adds an "s" to the title!
    string = "From 1-800-"+phoneGroup.upper()[:3]+"-"+(self.factString if hasattr(self, "factString") else "FACT")+": " + string
    return string
    
  def getJoke(self):
    joke = super().getJoke()
    if type(joke) == tuple: #If we have a picture, only make the message fun :)
      return (self.makeMessageFun(joke[0]), joke[1])
    return self.makeMessageFun(joke)
    
  def postSubscription(self, user, text):
    toSearch = self.title.split()[0].lower()
    if re.search(r"\b"+toSearch+r"s?\b", text): #If we found the "fact word" in their message (with optional s)
      addString = "\nFound " + toSearch + " in message!\nText '@Botsly unsubscribe from "+self.title+"s' at any time to unsubscribe"
      joke = self.getJoke()
      if type(joke) == tuple:
        joke = ((joke[0] + addString), joke[1])
      else:
        joke += addString
      return self._postJoke(user.group, joke)
    
#Internet fact is an interface for acquiring, posting, and saving facts from various internet sources
#Must be initialized with connection parameters and a function to filter raw data
#Filters facts on functions
#Inherits SimpleFileJoke for all the File methods, and SimpleFact for makeMessageFun
#  (note: most of this was copied from the original RedditFact)
class InternetFact(SimpleFileJoke, SimpleFact):
  TIMEOUT = 10 #Default timeout for internet requests

  #PRE: title should be a human-readable key for the group. Should be "x Fact" where x is "Fun" or "Bat"
  #     onJokeAcquire should be a function that takes a raw string of internet data and the empty jokes list, and populates the joke list
  #     urlDomain would be "www.reddit.com" or "www.google.com"
  #     urlLocation would be "/r/whatever"
  #     query should be a dict of queries like {"limit":"100"}
  #     headers should be a dict of headers like {"Thing":"is this"}
  #     HTTPS specifies if the requests should be over HTTP or HTTPS
  #     defaultJoke is the default joke
  def __init__(self, title, onJokeAcquire, urlDomain, urlLocation, query = {}, headers = {}, HTTPS = False, defaultJoke = defaultDefaultJoke):
    super().__init__(title, defaultJoke)
    self.onJokeAcquire = onJokeAcquire
    self.url = urlLocation
    self.query = query
    self.headers = headers
    
    self.connection = Network.Connection(urlDomain, https = HTTPS)
      
  def acquireJokes(self): #Gets new fact(s)
    XML_Dict = {"_":"http://www.w3.org/2005/Atom"}
  
    log.joke("Obtaining new",self.title+"s")
    log.network.low("Suppressing network for joke acquisition")
    try:
      webContent, code = self.connection.get(self.url, query = self.query, headers = self.headers, timeout = self.TIMEOUT)
    except OSError:
      log.web.debug("Socket Timed Out!")
      return False
    log.joke.debug("Code Received:",code)
    if code != 200: return False
    
    #Here is where most of the struggle comes from
    self.onJokeAcquire(webContent, self.jokes)
    
    if len(self.jokes) > 0:
      log.joke.debug("Acquired",len(self.jokes), self.title+"(s)")
    else:
      log.joke.error("No",self.title,"jokes were acquired!")
      return False
      
    #Save all jokes we got
    self.save()
    
    return True
    
  def getJoke(self):
    self.load()
    
    if len(self.jokes) == 0:
      if not self.acquireJokes():
        return self.defaultJoke #DEFAULT FACT
        
    #Will remove jokes so we don't get repeat jokes
    num = random.randrange(len(self.jokes))
    joke = self.jokes.pop(num)
    self.save() #Record that we removed the fact
    
    log.joke("Joke gotten,",len(self.jokes),"remaining")
    
    #Add in fun messages
    joke = (self.makeMessageFun(joke[0]), joke[1])
    
    #If we have a picture, return with a picture, otherwise just the joke
    #This is always a tuple here, so joke[1] would be None if no pic
    if joke[1]:
      return joke
    return joke[0]
  
    
#RedditFacts will get the most recent posts from reddit and return them (possibly with attached pictures) as "Facts" from a phony phone number
#Inherits from InternetFact and adds the concept of factFilters and its own filter function
class RedditFact(InternetFact):
  #PRE : title should be a human-readable key for the group. Should be "x Fact" where x is "Bat" or "Turtle" or whatever
  #      subreddit is the /r/subreddit to go to. defaultJoke is what is printed should nothing be able to be loaded
  #      if requirePictures is True (default False), getting facts will only acquire facts that have sendable pictures with them
  def __init__(self, title, subreddit, defaultJoke = defaultDefaultJoke, requirePictures = False):
    self.requirePictures = requirePictures
    self.factFilters = [] #This is a list of lambda functions that take in a string and return a modified string. Individual subreddits can filter the titles of their facts
    #The fact filter is used on message acquisition
  
    #getJokeFunc is defined below and returns a function with references to requirePictures and factFilters
    super().__init__(title, self.getJokeFunc(), "www.reddit.com", "/r/"+subreddit+"/.rss", query = {"limit":100}, headers = {
      "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
      "accept-encoding": "gzip, deflate, sdch, br",
      "accept-language": "en-US,en;q=0.8",
      "dnt": "1",
      "upgrade-insecure-requests": "1",
      "user-agent": "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36",
    }, HTTPS = True, defaultJoke = defaultJoke)
    
  def addFactFilter(self, filterFunc):
    if type(filterFunc) == type(lambda:None):
      self.factFilters.append(filterFunc)
      
  #Just a wrapper so we can get instance data in a static function
  def getJokeFunc(self):
    return lambda xmlFeed, jokes: RedditFact.onAcquire(xmlFeed, jokes, self.requirePictures, self.factFilters)
  
  #Can't be called onJokeAcquire because it overrides the variable
  @staticmethod
  def onAcquire(xmlFeed, jokes, requirePictures, factFilters): #This 100 most recent bat facts and returns them as a list of tuples (title, pictureUrl)
    XML_Dict = {"_":"http://www.w3.org/2005/Atom"}
  
    obj = xml.XML(xmlFeed)
    #NOTE: the list saved is a list of tuples of the form [0] = jokeText, [1] = jokeUrl (can be None)
    toSave = []
    pictureStrings = ["http://i.imgur.com","https://i.reddituploads.com", "https://upload.wikimedia.org", "http://66.media.tumblr.com"]
    for entry in obj.findall("_:entry", XML_Dict):
      title = entry.find("_:title", XML_Dict).text
      content = entry.find("_:content", XML_Dict).text
      link = None
      for string in pictureStrings:
        if string in content:
          #Find the link in the content, then split after it up to the next element
          endPart = content.split(string, 1)[1].split('"',1)[0].replace("&amp;","&") #&amp because weird formatting
          link = (string+endPart).replace(".gifv","") #Apparently imgur .gifv isn't supported, but just doing the imgur post is
          
      removeFact = False
      #Once we have acquired both, run our filters on the title before saving
      for func in factFilters:
        title = func(title)
        if not title:
          removeFact = True #If returns empty string or false, just get rid of joke altogether
          break
          
      if removeFact: continue #Break out of current iteration
          
      log.joke.low("----- NEW JOKE -----")
      log.joke.low("Title:", title)
      log.joke.low("Link: ", link)
      #If we don't have a picture link, we may or may not want to add the message
      if not requirePictures or link:
        toSave.append( (title, link) ) #Append a tuple of info
        
    #Now save all facts
    jokes.extend(toSave)
    
#A HybridFact takes a collection of other facts and randomly chooses from them
#Inherits from BaseJoke for most things, and SimpleFact for postSubscription
class HybridFact(BaseJoke):
  def __init__(self, title):
    super().__init__(title)
    self._handlers = [] #This is the list of joke handlers registered with us
    self._chosen = [] #List of joke handlers that have been used recently.
    
  #This simply adds the handler to our list for use
  def addHandler(self, handler):
    if handler not in self._handlers:
      self._handlers.append(handler)
      
  def getJoke(self):
    #This part is mostly copied from SimpleJoke
    if len(self._handlers) > 0:
      joke = None
      tries = 0 #We will only try a few different handlers
      while tries < (len(self._handlers) // 2 + 1): #Until we get a proper joke
        tries += 1
        #Pick a handler that hasn't been picked recently
        choice = random.choice([i for i in range(len(self._handlers)) if i not in self._chosen])
        joke = self._handlers[choice].getJoke()
        if joke:
          log.joke("Got a joke successfully from",self._handlers[choice])
          self._chosen.append(choice) #Add the handler to blacklist if it yielded a joke
          break
        else:
          log.joke.error("Joke get failed from", self._handlers[choice])
      #If we have gone through at least 3/4 of the jokes, start removing jokes from the blacklist
      if len(self._chosen) > (len(self._handlers) * 3 // 4):
        self._chosen.pop(0) #Will only fire if at least one element in list. No Error.
      return joke #Will return the joke regardless of us having one or not. Hopefully we got one
        
    #If we have no jokes, return the default one
    return defaultDefaultJoke
    
  #Uses its parent to do this
  def postSubscription(self, user, text):
    return SimpleFact.postSubscription(self, user, text)
      
  

### Include filters and name modules

#PRE: title is the title to filter, prefix is "Fun Fact\\:" or similar
def filterTitle(title, prefix):
  title = re.sub(r"^"+prefix+r"\s*", "", title, flags = re.I)
  title = re.sub(r"\(?x[- ]?post.+", "", title, flags = re.I)
  return title
  
def makeFilter(prefix): #Make filter functions that take only a title
  return lambda string: filterTitle(string, prefix)

def ignoreMeta(title):
  if re.search(r"\[meta\]", title, re.I):
    return False
  return title
  

### Define objects for use ###
joke          = StandardJoke()
pokemonJokes  = SimpleFileJoke("Pokemon Joke", "More like Relicant-th, amirite?!")
squirrelFacts = SimpleFact("Squirrel Fact", "Squirrels have big bushy tails!")
batFacts      = RedditFact("Bat Fact", "batfacts", "Uhh.... Bats have wings! *mumble* I don't get paid enough for this")
turtleFacts   = RedditFact("Turtle Fact", "TurtleFacts", "There is not a single fact that the internet gave me about turtles")
birdFacts     = RedditFact("Bird Fact", "BirdFacts", "Not many bird facts have pictures. Huh")
awwFacts      = RedditFact("Aww Fact","awwducational", "Animals are adorable")
snekFacts     = RedditFact("Snek Pic", "sneks", "Sneks are cute. Also reddit is stupid", requirePictures = True)
corgiFacts    = RedditFact("Corgi Pic", "corgi", "Corgis are strong, independent, and don't need no pictures to validate them", requirePictures = True)

## This section will be for all the constituents of fun facts
funFacts = HybridFact("Fun Fact")
haffFacts = RedditFact("Fun Fact 1","HeresAFunFact", "There are lots of fun facts in the world!")
haffFacts.addFactFilter(makeFilter(r"\[H?A?FF\]\:?"))
funFacts.addHandler(haffFacts)
darkFacts = RedditFact("Dark Fact","darkfacts")
darkFacts.addFactFilter(makeFilter(r"Dark Fact\:"))
funFacts.addHandler(darkFacts)
funFunFacts = RedditFact("Fun Fact 2","funfacts")
funFunFacts.addFactFilter(makeFilter(r"Fun Fact\:"))
funFacts.addHandler(funFunFacts)

def parseJSON(data, jokes):
  jokes.extend([(re.sub(r"\s*\<[^>]*\>\s*", " ", item['fact_body'], flags = re.I),"") for item in json.loads(data)])
  
mentalFlossFacts = InternetFact("Fun Fact 3", parseJSON, "www.mentalfloss.com", "/api/1.0/views/amazing_facts.json", query = {"limit":100, "display_id":"xhr"})
funFacts.addHandler(mentalFlossFacts)


### Add in text jokes ###
squirrelFacts.setJokes([
  ("Squirrels can find food buried beneath a foot of snow. Food is important during the cold winter months for squirrels. It makes sense, therefore, that some species are able to smell food under a foot of snow. The squirrel will then dig a tunnel under the snow, following the scent to their (or another squirrel’s) buried treasure.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2015/01/SquirrelSnow_PhotoContest-620x372.jpg"),
  ("A squirrel’s front teeth never stop growing. This is a common characteristic of other rodents, as well. The word “rodent” actually derives from the Latin “rodere,” which means to gnaw.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2012/04/JuvenileGraySquirrel_ChristineHaines.jpg"),
  ("Squirrels may lose 25% of their buried food to thieves. And that’s just from members of their own species! Scatter hoarders (squirrels with multiple caches of food) have a difficult time keeping an eye on all of their hidden food. Fellow squirrels or birds often take advantage of this for a free meal.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2015/01/Squirrel_Thief_PhotoContest-620x372.jpg"),
  ("They zigzag to escape predators. When squirrels feel threatened, they run away in a zigzag pattern. This is an incredibly useful strategy to escape hawks and other predators. Unfortunately, it doesn’t work so well on cars. Consider slowing down and giving squirrels a brake!", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2014/07/Inside2-620x413.jpg"),
  ("Squirrels may pretend to bury a nut to throw off potential thieves. Squirrels have been observed engaging in “deceptive caching.” This is where a squirrel digs a hole and vigorously covers it up again, but without depositing the nut. It seems this is done to throw off potential food thieves.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2015/01/Squirrel_Flickr_TomGill-620x372.jpg"),
  ("A newborn squirrel is about an inch long. If you come across one of these itty-bitty baby squirrels, please consult these resources, which will advise you what to do. That will help give the baby squirrel its best chance at survival.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2015/01/BabySquirrel_Flickr_Audrey-620x372.jpg"),
  ("Humans introduced squirrels to most of our major city parks. The story about why U.S. parks are full of squirrels is truly fascinating and worth a read.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2013/07/TiredSquirrel_BrianZingler_347659_620x422.jpg"),
  ("They get bulky to stay warm during the winter. Putting on some extra weight is one strategy squirrels use to stay warm during the cold winter months.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2013/12/squirrel-620x412.jpg"),
  (" Squirrels don’t dig up all of their buried nuts, which results in more trees! They have accidentally contributed countless trees to our nation’s forests. If you ask me, that’s a pretty great reason to appreciate squirrels.", "http://b50ym1n8ryw31pmkr4671ui1c64.wpengine.netdna-cdn.com/wp-content/blogs.dir/11/files/2015/01/SquirrelTree-620x372.jpg"),
  ("There is no amazing online community to find free squirrel facts like there was for batfacts. Therefore, there are less than 10 facts.", "http://mylolface.com/assets/faces/okay-okay.jpg")
  ])
  
  
  
### Utility Functions ###
#The only way this could have a problem is if we had "pokemon facts" and "pokemon jokes" or something like that
def getJokeType(string):
  for type in string.split():
    type = type.split(" ", 1)[0].title().strip(Events.PUNCTUATION_FILTER + " ")
    for word in ["Joke", "Fact", "Pic"]:
      try:
        return BaseJoke._jokeObjects[type+" "+word]
      except KeyError:
        pass
  return None