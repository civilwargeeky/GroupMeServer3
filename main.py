#"Shell" Script that launches mainServer and such

#main.py
#This file will download most recent files from dropbox folder, extract them to proper place, and restart the server.
#When server stops, will repeat the downloading. In case of errors, will send a groupMe message to the designated place, then wait and try again
#  it will try again every say, 5 minutes, and will send a message on success or failure first time, but none others

#Note: If the server stops due to an AssertionError, main interprets that as a request to return to the console of the server. It will not continue
#Note: You must install the "requests" library in order to use this

"""IMPORTANT NOTE: IN FILELIST, MAINSERVER.PY MUST GO LAST OR BAD THINGS!"""
#Actually, mainServer put into a main function. Shouldn't matter anymore...

import datetime
import time
import traceback
import os.path
import os

logName = "mainLog.txt"

def getDateString():
  return datetime.datetime.now().strftime("%y-%m-%d %H:%M:%S")
  
def writeLog(*arg):
  print(getDateString()+": "+" ".join(str(a) for a in arg))
  with open(logName,"a") as file:
    file.write(getDateString()+": ")
    for thing in arg:
      file.write(str(thing)+" ")
    file.write("\r\n")

def updateFiles(initial = False):
  import requests
  import zipfile
  import os.path
  import os
  import shutil
  import importlib
  
  
  filesURL = "http://www.dropbox.com/sh/18o2wz4tkppk7rb/AAAdKKLVHEOT1bfkXn-EcPNra?dl=1" #Botsly 2.0 File
  filesURL = "http://www.dropbox.com/sh/9vxt0vd523klwwu/AAANnsnJpW595GiObVcxSVRqa?dl=1" #Botsly 3.0 File (in release folder)
  tempZip = "DropboxFiles.zip"
  tempFolder = "DropboxFiles"
  fileListName = "fileList.txt"
  
  _tempURL = None
  writeLog("Attempting to read dropbox location file")
  try:
    with open("dropboxFile.txt") as file:
      _tempURL = file.read().rstrip()
  except:
    pass
  if _tempURL and "http://www.dropbox.com" in _tempURL:
    writeLog("dropbox location file found. New location to download:", _tempURL)
    filesURL = _tempURL
  
  writeLog("Starting update sequence!")
  
  #Aquiring new files from Dropbox as a zip file
  zipContent = requests.get(filesURL)
  zipFile = open(tempZip,"wb")
  zipFile.write(zipContent.content)
  zipFile.close()
  
  writeLog("zipfile aquired!")
  
  #Extracting from zip into temp directory
  zipReader = zipfile.ZipFile(tempZip)
  zipReader.extractall(tempFolder)
  zipReader.close()
  os.remove(tempZip)
  
  writeLog("zipfile extracted!")
  
  #We need to invalidate cache before loading new files (I think? Can't hurt)
  importlib.invalidate_caches()
  
  writeLog("caches invalidated")
  
  #Reading file list and overwriting
  with open(os.path.join(tempFolder, fileListName),"r") as listReader:
    fileList = [file.rstrip() for file in listReader]
  for file in fileList:
    writeLog("Loading",file)
    try:
      if os.path.isdir(os.path.join(tempFolder, file)):
        if os.path.exists(file): shutil.rmtree(file) #Remove it if exists already
        shutil.copytree(os.path.join(tempFolder, file), file)
      else:
        if os.path.exists(file): os.remove(file) #Remove the file before recopying
        shutil.copy(os.path.join(tempFolder,file),file)
        if os.path.exists(file):
          writeLog(" "*7,file," confirmed to exist!")
        else:
          writeLog("Essential file failed to copy. Erroring")
          raise FileNotFoundError("File "+file+" failed to copy")
          #Now we load after all files are copied
    except FileNotFoundError:
      writeLog("Failed to find file")
  for file in fileList:
    if ".py" in file and (not initial or file != "mainServer.py"): #If its a thing we need to load
      tempVar = importlib.import_module(file[:-3]) #Get a variable for the module (will load file if not loaded beforehand)(remove .py)
      importlib.reload(tempVar) #Will reload module if the module was already loaded.
  
  writeLog("Attempting to remove waste!")
  shutil.rmtree(tempFolder, ignore_errors=True) #Get rid of waste
  writeLog("Waste hopefully removed")

def main():
  #For just starting up
  #if not os.path.exists("mainServer.py"):
  #  writeLog("Essential files not found, updating")
  #  updateFiles(True)
  
  timesFailed = 0
    
  while True:
  
    #Always try to first update all the files
    try:
      #Once server stops, download new files
      updateFiles()
      
      #Don't reset counter if we just download the files
    except BaseException as E:
      with open("mainLog.txt","a") as file:
        file.write(getDateString())
        file.write(": Exception!\r\n")
        traceback.print_exc(file = file)
      timesFailed += 1
  
    try:
      #Start out by calling the main
      writeLog("Starting Main")
      import mainServer
      mainServer.main()
   
      #Reset counter
      timesFailed = 0
    except Exception as E:
      if isinstance(E, AssertionError):
        writeLog("Successful Nice Completion")
        return 0; #//Like C
        
      with open("mainLog.txt","a") as file:
        file.write(getDateString())
        file.write(": Exception!\r\n")
        traceback.print_exc(file = file)
      timesFailed += 1
      writeLog("Exception #"+str(timesFailed))
      
      
    #If did not succeed, wait
    if timesFailed > 0:
      writeLog("Unsuccessful Start. Times failed: ",timesFailed)
      sleepWait = min(60 * 60, 60 * 2 ** timesFailed)
      writeLog("Sleeping for "+str(sleepWait)+" seconds")
      time.sleep(sleepWait) #If failed, will sleep for an exponentially long time
      
if __name__ == "__main__":
  main()