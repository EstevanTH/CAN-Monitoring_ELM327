def _():
	global parametersFile
	global sequenceFile
	
	import inspect
	from sys import argv
	from os.path import isfile
	
	applicationDirectory = inspect.getfile( inspect.currentframe() )+"/../"
	parametersFile = applicationDirectory+"config/parameters.py"
	sequenceFile   = applicationDirectory+"config/sequenceELM327_CAN.py"
	
	def fixPath( filename ):
		fixedPath = None
		attemptedPaths = [
			filename,
			applicationDirectory+"config/"+filename,
		]
		for attemptedPath in attemptedPaths:
			if isfile( attemptedPath ):
				fixedPath = attemptedPath
				break
		return fixedPath
	
	for argument in argv:
		if argument[:13]=="--parameters=":
			parametersFile = fixPath( argument[13:] )
			break
	for argument in argv:
		if argument[:11]=="--sequence=":
			sequenceFile = fixPath( argument[11:] )
			break
_();del _

if parametersFile is None:
	print( "Could not locate the file specified for --parameters!" )
if sequenceFile is None:
	print( "Could not locate the file specified for --sequence!" )

if __name__=="__main__":
	print( "parametersFile =", parametersFile )
	print( "sequenceFile =", sequenceFile )
