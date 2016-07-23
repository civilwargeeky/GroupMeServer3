#Interface for lock objects and timers

import datetime
import threading

import Logging as log

class Holder:
  pass
  
holder = Holder()
holder._lockObj = None

def getLockObject():
  if not holder._lockObj:
    holder._lockObj = threading.Lock()
  return holder._lockObj
  
  
#The following functions are so we can nicely clean up threads in between server updates because I don't n
_threadList = []
def registerThread(thread):
  if thread not in _threadList:
    _threadList.append(thread)
    
def deregisterThread(thread):
  if thread in _threadList:
    _threadList.pop(_threadList.index(thread))
    
#This is a cleanup action and no threads will work anymore
def stopAllTimers():
  log.event("Stopping all timers")
  for thread in _threadList:
    thread.cancel()
  
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