"""
$Id: ImapHandler.py,v 1.4 2003/06/16 15:40:26 magnun Exp $
$Source: /usr/local/cvs/navbak/navme/subsystem/statemon/lib/handler/ImapHandler.py,v $
"""

from job import JobHandler
from event import  Event
import imaplib, Socket
class IMAPConnection(imaplib.IMAP4):
	def __init__(self, timeout, host, port):
		self.timeout=timeout
		imaplib.IMAP4.__init__(self, host, port)


	def open(self, host, port):
		"""
		Overload imaplib's method to connect to the server
		"""
		self.sock=Socket.Socket(self.timeout)
		self.sock.connect((self.host, self.port))
		self.file = self.sock.makefile("rb")

class ImapHandler(JobHandler):
	"""
	Valid arguments:
	port
	username
	password
	"""
	def __init__(self,service, **kwargs):
		JobHandler.__init__(self, "imap", service, port=143, **kwargs)
	def execute(self):
		args = self.getArgs()
		user = args.get("username","")
		ip, port = self.getAddress()
		passwd = args.get("password","")
		m = IMAPConnection(self.getTimeout(), ip, port)
		ver = m.welcome
		if user:
			m.login(user, passwd)
			m.logout()
		version=''
		ver=ver.split(' ')
		if len(ver) >= 2:
			for i in ver[2:]:
				if i != "at":
					version += "%s " % i
				else:
					break
		self.setVersion(version)
		
		return Event.UP, version

def getRequiredArgs():
	"""
	Returns a list of required arguments
	"""
	requiredArgs = ['username', 'password']
	return requiredArgs
			
