# Prints a message, prefixed with the current time
from datetime import datetime
def printT( *arguments ):
	print( datetime.now().strftime( "%H:%M:%S" ), *arguments )

# Include a Python script in Python 3
def execfile( filename, globalEnv ):
	f = open( filename )
	source = f.read()
	f.close()
	# Note: replacements of global variables in the included script are not passed to the parent script.
	return exec( compile( source, filename, 'exec' ), globalEnv )

# Include a Python script if it has been modified
from os import stat
from traceback import format_exc
def execfileIfNeeded( filename, globalEnv, fileInfo ):
	firstTimeLoaded = ( len(fileInfo)==0 )
	try:
		if "date" not in fileInfo:
			fileInfo["date"] = None
		if "size" not in fileInfo:
			fileInfo["size"] = None
		fileInfoCurrent = stat( filename )
		if fileInfoCurrent.st_size!=fileInfo["size"] or fileInfoCurrent.st_mtime!=fileInfo["date"]:
			if ( fileInfo["date"] is None ) or ( fileInfo["size"] is None ):
				printT( "Loading "+filename )
			else:
				printT( "Reloading "+filename )
			fileInfo["size"] = fileInfoCurrent.st_size
			fileInfo["date"] = fileInfoCurrent.st_mtime
			try:
				execfile( filename, globalEnv )
			except Exception as e:
				if firstTimeLoaded:
					raise e
				else:
					printT( format_exc() )
			return True
		else:
			return False
	except FileNotFoundError as e:
		if firstTimeLoaded:
			raise e

# Convert a dict object (bytes keys) into a JSON object as bytes, with JSONP support
def simpleDictionaryToJSON( source, callbackJSONP=None ):
	r = []
	for key in source.keys():
		dataValue = source[key]
		dataType = type( dataValue )
		if dataType is float or dataType is int:
			r.append( b'"'+key+b'":'+str( dataValue ).encode( "ascii" ) )
		elif dataType is bool:
			if dataValue:
				r.append( b'"'+key+b'":true' )
			else:
				r.append( b'"'+key+b'":false' )
		elif dataValue is None:
			r.append( b'"'+key+b'":null' )
		else:
			if dataType is bytes or dataType is bytearray:
				pass
			else:
				dataValue = str( dataValue ).encode( "utf_8", "replace" )
			r.append( b'"'+key+b'":"'+dataValue.replace( b'"',  b'\\"' )+b'"' )
	if callbackJSONP is None:
		return b'{\n'+b',\n'.join( r )+b'\n}'
	else:
		return callbackJSONP+b'({\n'+b',\n'.join( r )+b'\n});'

from os import name as os_name
isOsWindows = ( os_name=="nt" )

from os import system as os_system
if isOsWindows:
	def setConsoleColorWindows( colorCode ):
		os_system( "COLOR "+colorCode )
	def setConsoleTitle( title ):
		os_system( "TITLE "+title )
	def clearConsole():
		os_system( "CLS" )
else:
	def setConsoleColorWindows( colorCode ):
		pass
	def setConsoleTitle( title ):
		pass
	def clearConsole():
		os_system( "clear" )

try:
	bytes_hex = bytes.hex # Python 3.5+
except AttributeError:
	from binascii import b2a_hex
	def bytes_hex( data ):
		return b2a_hex( data ).decode( "ascii" )
