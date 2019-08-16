import http.server
import threading

from io import BytesIO
from utility import simpleDictionaryToJSON
from utility import printT
from utility import bytes_hex
from time import time
from socketserver import ThreadingMixIn
from websocket import WebSocketBadRequest, WebSocket
from json import dumps as json_dumps
from json import loads as json_loads
from urllib.parse import parse_qs
from traceback import format_exc

try:
	from http import HTTPStatus
except ImportError:
	import http.client as HTTPStatus # Python36 -> Python34


class WebSocket_frames(WebSocket):
	maxReceivedLen = 125 # only short frames
	allowFramesBinary = False
	allowFramesText = False
	
	def handleMessage( self, data ):
		""" Incoming message handler: nothing allowed """
		pass
	
	@classmethod
	def broadcastFrame( self, frame ):
		""" Broadcast a new frame (as JSON) - possible bottleneck """
		self.broadcastMessageText( simpleDictionaryToJSON( {
			b"t": frame.time,
			b"i": frame.identifier,
			b"e": frame.isExtended,
			b"r": frame.isRTR,
			b"l": frame.DLC,
			b"d": bytes_hex( frame.data ),
		} ) )


class Status( Exception ):
	status = 0
	text = "Something occurred"
	def __init__( self ):
		Exception.__init__( self, self.text )
class StatusBadRequest( Status ):
	status = HTTPStatus.BAD_REQUEST
	text = "Bad Request"
class StatusNotFound( Status ):
	status = HTTPStatus.NOT_FOUND
	text = "Not Found"
class StatusMethodNotAllowed( Status ):
	status = HTTPStatus.METHOD_NOT_ALLOWED
	text = "Method Not Allowed"
class StatusLengthRequired( Status ):
	status = HTTPStatus.LENGTH_REQUIRED
	text = "Length Required"
class StatusPayloadTooLarge( Status ):
	status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
	text = "Payload Too Large"


class CANCaptureHTTPRequestHandler( http.server.BaseHTTPRequestHandler ):
	# Based on http.server.SimpleHTTPRequestHandler
	server_version = "ELM327 CAN bus monitoring"
	protocol_version = "HTTP/1.1" # mandatory for WebSocket
	runWebSocket = False
	webSocketClass = None
	staticFiles = {
		"/show_dataframes.css": u"www/show_dataframes.css",
		"/show_dataframes.htm": u"www/show_dataframes.htm",
		"/show_dataframes.setup.js": u"www/show_dataframes.setup.js",
		"/show_dataframes.frames.js": u"www/show_dataframes.frames.js",
	}
	maxPostLength = 65536
	
	def do_GET( self ):
		f = None
		try:
			f = self.send_head()
			self.copyfile( f, self.wfile )
		except ConnectionError:
			return
		finally:
			if f is not None:
				f.close()
			del f
		
		if self.runWebSocket:
			try:
				ws = self.webSocketClass( self )
				ws.run()
			except ConnectionError:
				pass
			except StopIteration:
				pass
			except WebSocketBadRequest as e:
				printT( repr( e ) )
				return
	
	def do_HEAD( self ):
		f = None
		try:
			f = self.send_head( headersOnly=True )
		except ConnectionError:
			return
		finally:
			if f is not None:
				f.close()
			del f
	
	do_POST = do_GET
	
	@classmethod
	def postFieldToIdentifier( cls, identifier ):
		try:
			if isinstance( identifier, str ):
				if not len( identifier ):
					# empty string
					identifier = None
				else:
					# hexadecimal string
					identifier = int( identifier, base=16 )
					if identifier>0x1FFFFFFF or identifier<0:
						raise ValueError()
			else:
				# should be a number
				identifier = int( identifier )
		except TypeError:
			raise StatusBadRequest()
		except ValueError:
			raise StatusBadRequest()
		return identifier
	@classmethod
	def postFieldToIdentifiersSet( cls, postData, fieldName ):
		identifiers = postData[fieldName]
		if isinstance( identifiers, list ):
			# list of identifiers
			identifiers_temp = set( identifiers )
		elif not len( identifiers ):
			# empty string => None
			identifiers_temp = None
		else:
			# single identifier
			identifiers_temp = {identifiers}
		if identifiers_temp is None:
			identifiers = None
		else:
			identifiers = set()
			for identifier in identifiers_temp:
				identifiers.add( cls.postFieldToIdentifier( identifier ) )
		return identifiers
	
	def send_head( self, headersOnly=False ):
		headers = {}
		
		currentThread = threading.currentThread()
		currentThread.name = "%s %s"%(self.command, self.path)
		path = self.path.split( "?", 1 )[0]
		
		if path=="/frames.ws":
			self.webSocketClass = WebSocket_frames
			info = WebSocket.prepareHeaders( self )
			encoded = info["encoded"]
			response = info["response"]
			contentType = info["contentType"]
			headers = info["headers"]
		elif path=="/threads.txt":
			contentLines = [b"List of known running threads:"]
			currentThread = threading.currentThread()
			for thread in threading.enumerate():
				if thread is currentThread:
					contentLines.append( ( "%5u: This request"%(
						thread.ident or 0,
					) ).encode( "utf_8", errors="replace" ) )
				else:
					threadModuleName = str( thread.run.__func__.__module__ )
					threadClassName = type( thread ).__name__
					threadTargetClassName = None
					if type( thread ) is threading.Thread: # is not of a meaningful class
						try:
							threadTargetClass = type( thread._target.__self__ )
							threadModuleName = str( threadTargetClass.__module__ )
							threadClassName = str( threadTargetClass.__name__ )
						except:
							pass
					contentLines.append( ( "%5u: %s.%s(%s, %s) [%s]"%(
						thread.ident or 0,
						threadModuleName,
						threadClassName,
						str( thread._args )[1:-1],
						str( thread._kwargs )[1:-1],
						thread.name,
					) ).encode( "utf_8", errors="replace" ) )
			contentLines.append( b"\r\nOn Windows the CPU usage can be monitored for each thread using SysInternals Autoruns." )
			encoded = b"\r\n".join( contentLines )
			response = HTTPStatus.OK
			contentType = "text/plain"
		elif path[:5]=="/api/":
			contentType = "application/json"
			response = HTTPStatus.OK
			errorString = None
			data = {}
			canBus = self.server.thread.canBus
			try:
				postData = None
				if self.command=="POST":
					postContentLength = None
					try:
						postContentLength = int( self.headers.get( "Content-Length" ) )
					except TypeError:
						pass
					except ValueError:
						pass
					if postContentLength is None or postContentLength<0:
						raise StatusLengthRequired()
					if postContentLength>self.maxPostLength:
						raise StatusPayloadTooLarge()
					postPayload = self.rfile.read( postContentLength )
					postContentType = self.headers.get( "Content-Type", "application/x-www-form-urlencoded" )
					if postContentType[:16]=="application/json":
						try:
							postData = json_loads( postPayload.decode( "utf_8" ) )
						except ValueError:
							pass
					elif postContentType[:33]=="application/x-www-form-urlencoded":
						postData_ = None
						try:
							postData_ = parse_qs( postPayload.decode( "ascii" ), keep_blank_values=True, strict_parsing=True )
						except ValueError:
							pass
						if postData_ is not None:
							postData = {}
							for pair in postData_.items():
								# dict of lists => dict of {str and lists}
								if pair[0][-2:]=="[]":
									# explicit list
									postData[pair[0][:-2]] = pair[1]
								elif len( pair[1] )==1:
									# single str
									postData[pair[0]] = pair[1][0]
								else:
									# implicit list
									postData[pair[0]] = pair[1]
						del postData_
					if postData is None:
						raise StatusBadRequest()
				# Note: each POST data can be str or list or int!
				if   path=="/api/filter1/installByMask":
					if postData is None:
						raise StatusMethodNotAllowed()
					try:
						mask = self.postFieldToIdentifier( postData["mask"] )
						maskingResult = self.postFieldToIdentifier( postData["maskingResult"] )
					except KeyError:
						raise StatusBadRequest()
					canBus.setFilter1Remote( mask, maskingResult )
				elif path=="/api/filter1/installByIds":
					if postData is None:
						raise StatusMethodNotAllowed()
					try:
						whitelist = self.postFieldToIdentifiersSet( postData, "whitelist" )
					except KeyError:
						raise StatusBadRequest()
					if whitelist is None:
						# only vanish whitelist
						canBus.setFilter1Local( None )
					else:
						# set filter as well
						canBus.setFilter1( whitelist )
				elif path=="/api/filter1/getInstalled":
					maskInfo = canBus.getFilter1Remote()
					data["mask"] = maskInfo[0]
					data["maskingResult"] = maskInfo[1]
					del maskInfo
					whitelist = canBus.getFilter1Local()
					whitelist = ( whitelist is not None ) and list( whitelist ) or None
					data["whitelist"] = whitelist
					del whitelist
				elif path=="/api/filter1/reset":
					if postData is None:
						raise StatusMethodNotAllowed()
					canBus.setFilter1( None )
				elif path=="/api/filter2/setExcluded":
					if postData is None:
						raise StatusMethodNotAllowed()
					try:
						blacklist = self.postFieldToIdentifiersSet( postData, "blacklist" )
					except KeyError:
						raise StatusBadRequest()
					canBus.setFilter2( blacklist )
				elif path=="/api/filter2/getExcluded":
					blacklist = canBus.getFilter2()
					blacklist = ( blacklist is not None ) and list( blacklist ) or None
					data["blacklist"] = blacklist
					del blacklist
				elif path=="/api/filter2/reset":
					if postData is None:
						raise StatusMethodNotAllowed()
					canBus.setFilter2( None )
				elif path=="/api/setInactivityTimeout":
					if postData is None:
						raise StatusMethodNotAllowed()
					try:
						inactivityTimeout = float( postData["timeout"] )
					except TypeError:
						raise StatusBadRequest()
					except ValueError:
						raise StatusBadRequest()
					if inactivityTimeout<=0.:
						raise StatusBadRequest()
					canBus.inactivityTimeout = inactivityTimeout
				elif path=="/api/getInactivityTimeout":
					data["timeout"] = canBus.inactivityTimeout
				else:
					raise StatusNotFound()
			except Status as e:
				response = e.status
				errorString = e.text
			except Exception as e:
				printT( format_exc() )
				response = HTTPStatus.INTERNAL_SERVER_ERROR
				errorString = repr( e )
			del canBus
			if response==HTTPStatus.OK:
				data["status"] = 200
			else:
				data = {
					"status": int( response ),
					"error": errorString,
				}
			encoded = json_dumps( data ).encode( "utf_8", errors="replace" )
		elif path in self.staticFiles:
			diskFileExcept = None
			try:
				diskFile = open( self.staticFiles[path], "rb" )
				encoded = diskFile.read()
				diskFile.close()
				response = HTTPStatus.OK
				ext_4 = path[-5:].lower()
				ext_3 = ext_4[-4:]
				ext_2 = ext_4[-3:]
				contentType = "application/octet-stream"
				if ext_3==".htm" or ext_4==".html":
					contentType = "text/html; charset=utf-8"
				elif ext_2==".js":
					contentType = "text/javascript"
				elif ext_3==".css":
					contentType = "text/css"
			except FileNotFoundError as e:
				diskFileExcept = e
				response = HTTPStatus.NOT_FOUND
			except PermissionError as e:
				diskFileExcept = e
				response = HTTPStatus.FORBIDDEN
			except Exception as e:
				printT( format_exc() )
				diskFileExcept = e
				response = HTTPStatus.INTERNAL_SERVER_ERROR
			if diskFileExcept:
				encoded = repr( diskFileExcept ).encode( "utf_8", "replace" )
				contentType = "text/plain"
		else:
			encoded = b"Not found"
			response = HTTPStatus.NOT_FOUND
			contentType = "text/plain"
		
		f = BytesIO()
		f.write( encoded )
		f.seek( 0 )
		self.send_response( response )
		if contentType is not None:
			self.send_header( "Content-type", contentType )
		if headersOnly:
			self.send_header( "Content-Length", "0" )
		else:
			self.send_header( "Content-Length", str( len( encoded ) ) )
		for header in headers.items():
			self.send_header( header[0], header[1] )
		self.send_header( "Access-Control-Allow-Origin", "*" )
		self.end_headers()
		return f
	
	copyfile = http.server.SimpleHTTPRequestHandler.copyfile
	
	def log_request( self, code='-', size='-' ):
		pass # no logging for successful requests


class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
	daemon_threads = True


class CANCaptureHTTPServerThread( threading.Thread ):
	daemon = True # exit immediatly on program exit
	
	def __init__( self, vehicleData, canBus, ipAddress="127.0.0.1", tcpPort=8327 ):
		threading.Thread.__init__( self )
		if ":" in ipAddress:
			# IPv6
			self.name = "[%s]:%u"%(ipAddress, tcpPort)
		else:
			# IPv4
			self.name = "%s:%u"%(ipAddress, tcpPort)
		self.canBus = canBus
		self.ipAddress = ipAddress
		self.tcpPort = tcpPort
	
	def getParameters( self ):
		return {
			"ipAddress": self.ipAddress,
			"tcpPort": self.tcpPort,
		}
	
	def run( self ):
		httpd = ThreadedHTTPServer( (self.ipAddress, self.tcpPort), CANCaptureHTTPRequestHandler )
		httpd.thread = self
		printT( "CANCaptureHTTPServerThread started:", self.ipAddress, self.tcpPort )
		httpd.serve_forever()
