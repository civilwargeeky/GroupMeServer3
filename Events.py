#Interface for lock objects and timers

import datetime
import os
import threading

import Logging as log

### CROSS-MODULE CONSTANTS ###
IS_TESTING = os.path.basename(os.getcwd()) in ["test","dev"]
ADDRESS_MODIFIERS = ["college"]
PUNCTUATION_FILTER = ".,/?!'\";:@#$%^&*()[]{}<>*-+="

### EVENTS AND UPDATING ###
class Holder:
  pass
  
holder = Holder()
holder._lockObj = None

def getLockObject():
  if not holder._lockObj:
    holder._lockObj = threading.Lock()
  return holder._lockObj
  
#I'm not sure why I used a holder object above... rather than just having a lock object here
NonBlockingShutdownLock = threading.Lock() #This is so processes can tell the server to shutdown
NonBlockingRestartLock  = threading.Lock() #This is so processes can tell the server to restart

def quickDaemonThread(function):
  threading.Thread(target = function, daemon = True).start()
  
#The following functions are so we can nicely clean up threads in between server updates because I don't n
_threadList = []
def registerThread(thread):
  if thread not in _threadList:
    _threadList.append(thread)
    
def deregisterThread(thread):
  if thread in _threadList:
    _threadList.pop(_threadList.index(thread))
    
#This is a cleanup action and no timers will work anymore
def stopAllTimers():
  log.event("Stopping all timers")
  for thread in _threadList:
    thread.cancel()
    
    
#These are for saving all groups who have added messages at once (not during message processing so responses are fast always)
_SyncSave_ = None #This is the actual object
def SyncSave():
  global _SyncSave_
  if not _SyncSave_:
    _SyncSave_ = _SyncSave()
  return _SyncSave_ #Return the object we have

class _SyncSave:
  def __init__(self, interval = 60):
    self.interval = interval #Interval between saves in seconds
    self._objects = [] #The list of all object we have
    
    self.timer = None
    #Start a timer that runs every so many seconds
    self.resetTimer()
  
  def resetTimer(self):
    if self.timer:
      self.timer.cancel()
      deregisterThread(self.timer) #Stop tracking it
      del self.timer #Remove reference (I guess this is good, probably not necessary)
      
    self.timer = threading.Timer(self.interval, self.saveAll)
    self.timer.daemon = True #Screw not being able to close the prompt
    registerThread(self.timer)
    self.timer.start()
  
  def addObject(self, object):
    if object in self._objects:
      return None #Don't worry if we already have it
    self._objects.append(object)
    
  def saveAll(self, final = False):
    try:
      if len(self._objects): # if != 0
        log.event("Saving all messages for",len(self._objects),"group"+("s" if len(self._objects) > 1 else ""))
        while len(self._objects): #While there are still objects in the list
          object = self._objects.pop() #Take it off and use it
          object._save() #_save must be a function that DOES NOT CALL addObject
    finally: #Whether or not we are successful, add another timer
      if not final:
        self.resetTimer()
    
    
  
class PeriodicUpdater():
  #A peridodic updater takes a referenceTime time (say, 2 a.m.) and a timedelta (say, 1 week or 1 day)
  #Every update, the object will set a timer to occur timedelta after the referenceTime
  def __init__(self, referenceTime, timedelta, function, argsList = [], argsDict = {}):
    if type(referenceTime) != datetime.time:
      raise TypeError("referenceTime must be a datetime.time object, got " + str(type(referenceTime)))
    if type(timedelta) != datetime.timedelta:
      raise TypeError("timedelta must be a datetime.timedelta object, got " + str(type(timedelta)))
    if timedelta.days <= 0:
      raise ValueError("timedelta must be at least one day")
      
    self.referenceTime = referenceTime
    self.timedelta     = timedelta
    self.function      = function
    self.arg           = argsList
    self.kwarg         = argsDict
    
    self.timerObj = None
    self.resetTimer(initial = True) #Starts the given function
    
  #Cancels the timer (if it exists)
  def cancel(self):
    try:
      self.timerObj.cancel()
    except AttributeError:
      pass
    
  def resetTimer(self, initial = False):
    if self.timerObj:
      self.timerObj.cancel() #Does not care if timer is alive
      
    #if initial will try to set it to the referenceTime today
    nextTrigger = (datetime.datetime.combine(datetime.date.today(), self.referenceTime) + (datetime.timedelta(0) if initial else self.timedelta))
    if nextTrigger < datetime.datetime.now(): #If the trigger is in the past
      nextTrigger += datetime.timedelta(days = 1) #Set the trigger to tomorrow
    log.event("Setting new trigger for", str(nextTrigger))
    #Express the difference in time between the next trigger and now as an integer for the timer to wait
    difference = int((nextTrigger - datetime.datetime.now()).total_seconds())+1 #+1 because it rounds down to 23 hours 59 mins, 59 seconds
    log.event.debug("Trigger will fire in",str(datetime.timedelta(seconds = difference)))
    
    #First stop tracking this one
    deregisterThread(self.timerObj)
    del self.timerObj
    
    #And track the next one once it is made
    self.timerObj = threading.Timer(difference, self.startFunction)
    registerThread(self.timerObj)
    self.timerObj.daemon = True #We don't want this thread blocking system exit
    self.timerObj.start() #Starts the timer
    
  def startFunction(self):
    log.event("PeriodicUpdater acquiring thread to run function")
    lock = getLockObject()
    lock.acquire() #Wait for whatever other function is executing now to finish
    try:
      self.function(*self.arg, **self.kwarg)
    finally: #Whether or not it errors we need to release the lock and reset the function
      lock.release()
      self.resetTimer() #Sets the next iteration