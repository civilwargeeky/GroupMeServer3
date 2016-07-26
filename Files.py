#File interface for various tasks and functions within the program
#Provides container objects that can be easily made, loaded, and saved.

import json
import os
import shutil

import Logging as log

#### Get Local Files Names ####
join = os.path.join #So we can do Files.join in other places

def getFileName(name, prefix = "LOG_", ext = "txt"):
  #Splits the name into folder section, then joins it to the name, which has been modified with "LOG" and an extension
  return os.path.normpath(os.path.join(os.path.dirname(name),prefix+os.path.basename(name)+"."+ext))
  
def getGroupFolder(group):
  return "Group {:d}".format(group.ID)
  
def getGroupFileName(group, fileName): #Return the file name in the group's folder
  return getFileName(getGroupFolder(group)+"/"+fileName, prefix = "")

def getFilesInDir(directory = None): #Returns the filenames of all files, appended with the directory name
  return [os.path.join(directory or "", file) for file in os.listdir(directory) if os.path.isfile(os.path.join(directory or "", file))]
  
def getDirsInDir(directory = None): #Returns the filenames of all files, appended with the directory name
  return [os.path.join(directory or "", file) for file in os.listdir(directory) if os.path.isdir(os.path.join(directory or "", file))]
  
#Creation and deletion
  
def createFolder(directory): #Creates a folder if it does not exist
  if not os.path.exists(directory):
    log.file("Path to", directory, "does not exist! Creating folders")
    os.makedirs(directory)
    
def deleteFolder(directory): #Deletes folder and all subfolders
  shutil.rmtree(directory, ignore_errors=True)
  
def deleteFile(file):
  if os.path.exists(file):
    try:
      os.remove(file)
      return True
    except OSError:
      log.file.error("Could not remove file:",file)
      return False

#### Utilities ####
def write(file, text): #Writes text with a newline
  file.write(text)
  file.write("\n")
  
def read(file): #Reads a line of text, stripping newline
  toRet = file.readline().rstrip()
  log.file.low("Reading:", toRet)
  return toRet
  
#Saves a set of attributes as a json dict
#PRE: table is an iterable of keys to save from the object
def saveAttrTable(obj, handle, table):
  json.dump({key:getattr(obj, key) for key in table}, handle)
  handle.write("\n")
  
def loadAttrTable(obj, handle):
  text = read(handle)
  if "{" in text: #If there is any JSON there at all
    data = json.loads(text) #Load the json file
    for attr in data: #Set all the attributes we saved
      setattr(obj, attr, data[attr])
      
#Saves a dict/list to file
def saveTable(handle, table):
  json.dump(table, handle)
  handle.write("\n")
  
def loadTable(handle):
  text = read(handle)
  try:
    return json.loads(text) #Load the json file, return it
  except json.decoder.JSONDecodeError:
    log.file.error("Could not load json file")
    return None #If we can't load the object, say we can't load the object
  
#Loads tokens from a file
TOKEN_FILE_NAME = getFileName("my_tokens")
TOKEN_LIST = []
#Can be overridden to get new every time
def getTokenList(override = False):
  global TOKEN_LIST
  if TOKEN_LIST and not override:
    return TOKEN_LIST
  #Otherwise
  try:
    with open(TOKEN_FILE_NAME) as file:
      toRet = loadTable(file) #Should still close though
      if not toRet:
        raise RuntimeError("NO TOKENS LOADED FROM FILE") from None
      if not TOKEN_LIST:
       TOKEN_LIST = toRet
      return toRet
  except FileNotFoundError:
    log.error("COULD NOT LOAD TOKEN FILES, ERRORING")
    raise FileNotFoundError("COULD NOT FIND TOKEN FILE " + TOKEN_FILE_NAME) from None
  
#### Helpful Classes ####

class SafeOpen:
  def __init__(self, *arg, **kwarg):
    createFolder(os.path.dirname(arg[0]))
    self.file = open(*arg, **kwarg)
    
  def __enter__(self):
    return self.file
    
  def __exit__(self, *errors):
    self.file.close()
            
"""#Nifty function for displaying KB, MB, GB, etc.            
def sizeof_fmt(num, suffix='B'):
  for unit in ['','K','M','G','T']:
    if abs(num) < 1024 or unit == 'T':
      return "{:3.1f}{:s}{:s}".format(num, unit, suffix)
    num /= 1024.0
"""
            
class LogAccessor: #Meant to be used like "with LogAccessor(fileName) as file:"
  fileSize = 1 * 1024**2 #Log file size should be no more than 1 MB
  
  def __init__(self, fileName):
    fileName += "_"
    lastNum = 0
    try:
      while os.path.getsize(getFileName(fileName + str(lastNum))) > self.fileSize: #File should no more than max size
        lastNum += 1
    except FileNotFoundError:
      pass #Means we should make a new file
      
    self.file = open(getFileName(fileName + str(lastNum)), "ab")
  
  def __enter__(self):
    return self.file
    
  def __exit__(self, *errors):
    self.file.close()