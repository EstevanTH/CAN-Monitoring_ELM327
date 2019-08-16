import threading
from traceback import format_exc
from utility import printT
from CANCaptureHTTPServer import WebSocket_frames

class CANCaptureFrameHandler( threading.Thread ):
	"""
	Thread that delegates the work of CAN frames handling for improved timings
	Particular attention is needed for thread safety.
	"""
	
	daemon = True
	asyncException = None # exception caught in the process, re-raised on frame income
	
	def __init__( self, canSource ):
		threading.Thread.__init__( self )
		self.canSource = canSource
		
		self.pendingFrames = None
		self.pendingFramesLock = threading.Lock()
		
		self.continueProcessLock = threading.Lock()
		self.continueProcessLock.acquire()
	
	def handleNewFrame( self, frame ):
		if self.asyncException is not None:
			asyncException = self.asyncException
			self.asyncException = None
			raise asyncException
		else:
			self.pendingFramesLock.acquire()
			self.pendingFrames.append( frame )
			self.pendingFramesLock.release()
			try:
				self.continueProcessLock.release()
			except RuntimeError:
				pass
	
	def run( self ):
		canSource = self.canSource
		self.pendingFrames = []
		while True:
			self.continueProcessLock.acquire()
			presentPendingFrames = True
			while presentPendingFrames:
				self.pendingFramesLock.acquire()
				pendingFrames = self.pendingFrames
				self.pendingFrames = [] # cleanup
				self.pendingFramesLock.release()
				presentPendingFrames = len( pendingFrames )!=0
				for frame in pendingFrames:
					try:
						if canSource.passesFilters( frame ): # thread-safety required
							WebSocket_frames.broadcastFrame( frame )
							if canSource.canExporter is not None:
								canSource.canExporter.logFrame( frame )
					except Exception as asyncException:
						# This exception will be raised on next frame income, with an incorrect stack trace.
						self.asyncException = asyncException
						printT( format_exc() )
