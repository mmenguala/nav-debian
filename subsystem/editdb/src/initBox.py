#!/usr/bin/env python

from socket import inet_aton,error,gethostbyname,gethostbyaddr
from nav.Snmp import Snmp,NameResolverException,TimeOutException
from nav.db import getConnection

class Box:
    """
    Object that gets ip,hostname,sysobjectid and snmpversion when initialized
    """


    def __init__(self,identifier,ro):
        """
        Initialize the object, and get all the values set.
        The values = ip, hostname, sysobjectid and snmpversion

        - identifier : hostname or ip
        - ro         : read-only snmp community
        """
        # deviceIdList must be list, not tuple
        self.deviceIdList = []
        self.ro = ro
        (self.hostname,self.ip) = self.getNames(identifier)
        self.typeid = self.getType(identifier,ro)
        self.snmpversion = self.getSnmpVersion(identifier,ro)
        self.serial = ''


    def getNames(self,identifier):
        """
        Gets the proper IP-address and hostname, when only one of them are defined.

        - identifier : hostname or ip

        returns (hostname, ip-address)
        """

        #id er hostname
        hostname = identifier
        try:
            ip = gethostbyname(hostname)
        except error, e:

            ip = identifier
            try:
                #id er ip-adresse
                ip = inet_aton(identifier)
                hostname = gethostbyaddr(ip)[0]
                
            except error:
                #raise NameResolverException("No IP-address found for %s" %hostname)
                hostname = ip
        return (hostname,ip)


    def getType(self,identifier,ro):
        """
        Get the type from the nav-type-table. Uses snmp-get and the database to retrieve this information.

        - identifier: hostname or ip-address
        - ro: snmp read-only community

        returns typeid
        """
        
        snmp = Snmp(identifier, ro)

        sql = "select snmpoid from snmpoid where oidkey='typeoid'"
        connection = getConnection("bokser")
        handle = connection.cursor()
        handle.execute(sql)
        oid = handle.fetchone()[0]
        
        sysobjectid = snmp.get(oid)
        
        self.sysobjectid = sysobjectid.lstrip(".")

        typeidsql = "select typeid from type where sysobjectid = '%s'"%self.sysobjectid
        handle.execute(typeidsql)
        try:
            typeid = handle.fetchone()[0]
        except TypeError:
            typeid = None
        #hae? hva gj�r denne?
        snmpversion = 1

        return typeid

    def __getSerials(self,results):
        """
        Does SQL-queries to get the serial number oids from the database. This function does no snmp-querying.
        """

        snmp = Snmp(self.ip,self.ro,self.snmpversion)
        serials = []
        walkserials = []
        for oidtuple in results:
            oid = oidtuple[0]
            getnext = oidtuple[1]
            if not oid.startswith("."):
                oid = "."+oid
            try:
                if getnext==1:
                    result = snmp.walk(oid.strip())
                    if result:
                        for r in result:
                            if r[1]:
                                walkserials.append(r[1])
                else:
                    serials.append(snmp.get(oid.strip()).strip())

            except:
                pass

        serials.extend(walkserials)
        self.serials = serials
        self.serial = serials[0]
        return serials


    def getDeviceId(self):
        """
        Uses all the defined OIDs for serial number. When doing SNMP-request, the SNMP-get-results are prioritised higher than the SNMP-walk-results, because SNMP-gets are more likely will get one ("the one") serial number for a device.

        This function returns all deviceids for all serial numbers for all serial number oids that the device responded on.
        """
        
        connection = getConnection("bokser")
        handle = connection.cursor()

        serials = []
        type = self.typeid
        if type:
            sql = "select snmpoid,getnext from snmpoid left outer join typesnmpoid using (snmpoidid) where typeid = "+str(type)+" and oidkey ilike '%serial%'"
            handle.execute(sql)
            results = handle.fetchall()
            serials = self.__getSerials(results)

        if not serials:
            sql = "select snmpoid,getnext from snmpoid where oidkey ilike '%serial%'"
            handle.execute(sql)
            results = handle.fetchall()
            serials = self.__getSerials(results)
            
        devlist = []
        sqlserials = []
        for ser in serials:
            sqlserials.append("serial='%s'"%ser)
        serial = str.join(" or ",sqlserials)
        sql = "select deviceid,productid from device where %s" % serial
        handle.execute(sql)
        for record in handle.fetchall():
            devlist.append(record[0])

        if devlist:
            self.deviceIdList = devlist
            return devlist
     
    def getSnmpVersion(self,identifier,ro):
        """
        Uses different versions of the snmp-protocol to decide if this box uses version 1 or 2(c) of the protocol

        - identifier: hostname or ip-address
        - ro: snmp read-only community

        returns the protocol version number, 1 or 2 (for 2c)
        """

        snmp = Snmp(identifier,ro,"2c")

        try:
            sysname = snmp.get("1.3.6.1.2.1.1.5.0")
            version = "2c"
        except TimeOutException:

            snmp = Snmp(identifier,ro)
            try:
                sysname = snmp.get("1.3.6.1.2.1.1.5.0")
                version = "1"
            except TimeOutException:
                version = "0"
            
        return version

    def getBoxValues(self):
        """
        Returns all the object's values
        """
        
        return self.hostname,self.ip,self.typeid,self.snmpversion

        
## sql = "select ip,sysname,ro from netbox where snmp_version > 0 and catid <> 'SRV'"
## connection = getConnection("bokser")
## handle = connection.cursor()
## handle.execute(sql)
## for record in handle.fetchall():
##     print repr(record)
##     try:
##         a = Box(record[0],record[2])
##         #print a.getBoxValues()
##         print a.getDeviceId()
##     except:
##         print "FEIL: " + record[1]+" fikk ikke fornuftig svar"
##     print "\n"

#a = Box("129.241.23.14","idija")
#print a.getDeviceId()
#print a.serial
