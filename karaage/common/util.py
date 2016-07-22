#!/usr/bin/python

from __future__ import absolute_import
import os, sys, random, string, traceback, json, datetime, re
from django.contrib.auth.models import User
from django.db.models import Q
from karaage.people.models import Person
from karaage.people.forms import AddPersonForm, AdminPersonForm, PersonForm
from karaage.projects.models import Project
from karaage.machines.models import MachineCategory
import logging
from django.conf import settings
from karaage.institutes.models import Institute
from karaage.machines.models import Account
from karaage.people.models import Person, Group

unsafe_list = "[^a-z0-9]" 

logger = logging.getLogger(__name__)

USER_LOG_FILE = "/var/local/user_log/hpcid_users.log"

class Util(): 
    
    username_list = []
    
    def __init(self):
        projectId = "pCvl"

    @classmethod
    def log(self, message):
        logger.debug(message)

    @classmethod
    def warning(self, message):
        logger.error(message)

    @classmethod
    def user_log(self, message):
        if os.access(os.path.dirname(USER_LOG_FILE), os.W_OK):
            with open(USER_LOG_FILE, "a") as log:
                log.write(message)
        else:
            self.warning("Disable generating user list log") 

    @classmethod
    def parseShibAttributes(self, request):
        shib_attrs = {}
        error = False
        for header, attr in settings.SHIB_ATTRIBUTE_MAP.items():
            required, name = attr
            values = request.META.get(header, None)
            value = None
            if values:
                try:
                    value = values.split(';')[0]
                except:
                    value = values

            shib_attrs[name] = value
            if not value or value == '':
                if required:
                    error = True
        if error:
            error = self.parseAttributes(shib_attrs, error)
        return shib_attrs, error
         
    @classmethod
    def parseAttributes(self, attr, error):
        if error:
            if 'first_name' in attr and 'full_name' in attr and 'last_name' in attr:
                if not attr['first_name']:
                    if attr['full_name'] and attr['last_name']:
                        attr['first_name'] = self.getFirstName(attr['full_name'], attr['last_name'])
                        error = False
        return error    

    @classmethod
    def getFirstName(self, commonName, lastName):
        lastNameLength = len(lastName)
        commonNameLength = len(commonName)
        firstName = commonName[0 : commonNameLength - lastNameLength - 1]
        return firstName
    
    @classmethod
    def getUniqueUsernameList(self, dict = {}):
        udict = {}
        for key, value in dict.items():
            if not self.findUsername(value):
                udict[key] = value
        return udict

    @classmethod
    def setUniqueUsername(self, username):
        tail = 1
        conflict = True
        original_username = username
        while conflict:
            conflict = False
            if self.findUsername(username):
                username = original_username + str(tail)
                tail = tail + 1
                conflict = True
        return username 

    @classmethod
    def getUniqueUsername(self, username, usernames = {}):
        uname = None 
        if not username in usernames:
            uname = username
            tail = 1
            conflict = True
            while conflict:
                conflict = False
                if self.findUsername(uname):
                    uname = uname + str(tail)
                    tail = tail + 1
                    conflict = True
        return uname

    @classmethod
    def setUsername(self, commonName, lastName, eppn = None):
        if not self.username_list:
            firstName = self.getFirstName(commonName, lastName) 
            pFirstName = self.posixName(firstName.lower())
            pLastName = self.posixName(lastName.lower())

            username = pFirstName[0] + pLastName[:7]
            username = self.setUniqueUsername(username)
            self.username_list.append(username)
        
            username = pFirstName[:7] + pLastName[0]
            username = self.setUniqueUsername(username)
            self.username_list.append(username)

            if eppn:
                username = eppn[0:eppn.find("@")]
                if username not in self.username_list:
                    username = self.setUniqueUsername(username)
                    self.username_list.append(username)

    @classmethod
    def getPassword(self, length = 8):
        chars = string.ascii_letters + string.digits + '!@#$%^&*()'
        random.seed = (os.urandom(1024))
        password = ''.join(random.choice(chars) for i in range(length))
        return password
    
    @classmethod
    def findUsername(self, username):
        conflict = False 
        try:
            person = Person.objects.get(username = username)
            if person:
                conflict = True
        except Person.DoesNotExist:
            pass
        return conflict 
    
    @classmethod
    def searchPerson(self, id):
        person = None
        try:
            person = Person.objects.get(saml_id = id)
            self.log("Found person %s" % person.username)
        except Person.DoesNotExist:
            pass
        return person 
    
    @classmethod
    def findUser(self, request):
        user = None
        d, error = self.parseMetadata(request)
        if not error:
            user = self.searchPerson(d["saml_id"])
        return user

    @classmethod
    def parseMetadata(self, request):
        attr, error_message = self.parseShibAttributes(request)
        error = False
        if error_message:
            error = True
            return attr, error

        d = {}
        d["title"] = ""
        d["first_name"] = attr['first_name']
        d["surname"] = attr['last_name']
        d["full_name"] = attr['full_name']
        d["position"] = ""
        d["department"] = ""
        d["supervisor"] = ""
        d["email"] = attr['email']
        self.setUsername(attr['full_name'], attr['last_name'], attr['eppn'])
        d["username"] = self.username_list[0]
        d['password'] = "" 
#        d['password'] = self.getPassword()
        d["country"] = ""
        d["telephone"] = attr['telephone'] 
        d["mobile"] = ""
        d["fax"] = ""
        d["address"] = ""
        d["idp"] = attr['idp'] 
        d["short_name"] = attr['last_name'] 
        d['saml_id'] = attr['persistent_id']
        d['eppn'] = attr['eppn']
        return d, error

    @classmethod
    def aafbootstrap(self, request, id = None):
        new_user = False
        d, error = self.parseMetadata(request)
        if error:
            return new_user, error, None 
        person = self.searchPerson(d["saml_id"])
        if person:
            self.updateProfile(person, d)
        else:
            if id:
                d["username"] = id 
            person = self.addPerson(d)
            if person:
                new_user = True  
                user_log = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M") + ": " + d["username"] + " " + d['email'] + " " + d['eppn'] + " " + d['saml_id'] + "\n"
                self.user_log(user_log)
        return new_user, error, person 

    @classmethod
    def updateProfile(self, p, d):
        if p.email != d['email']:
            p.email = d['email']
            p.institute = Institute.objects.get(saml_entityid=d['idp'])
            self.log("Update user %s profile" % d['username'])
            p.save()

#    @classmethod
#    def getId(self, username, email):
        

    @classmethod
    def addPerson(self, d):
        person = None
        try:
            institute = self.getInstitute(d['idp'])
            if not institute:
                return None
            person = Person.objects.create(username = d['username'], password = d['password'], short_name = d['short_name'], full_name = d['full_name'], email = d['email'], institute = Institute.objects.get(saml_entityid = d['idp']), saml_id = d['saml_id'], is_active = True, date_approved = datetime.date.today())
            if person:
                if not person.saml_id:
                    person.saml_id = d['saml_id']
                    person.save()
                self.log("Create user account %s" %(person.username))
        except:
            self.warning("Failed to add person exception %s" % traceback.format_exc())
        return person

    @classmethod
    def isMember(self, p):
        member = False
        try:
            if hasattr(settings, "DEFAULT_PROJECT_PID"):
                project = Project.objects.get(pid = settings.DEFAULT_PROJECT_PID)
                if project and project.is_active:
                    members = project.group.members.filter(pk = p.pk)
                    if members.count() > 0:
                        member = True
        except:
            self.warning("Exception to search member in project: %s" % traceback.format_exc())
        return member

    @classmethod
    def getDefaultMachineCategory(self):
        mc = None
        if hasattr(settings, "DEFAULT_MACHINE_CATEGORY_NAME"):
            mc = MachineCategory.objects.get(name = settings.DEFAULT_MACHINE_CATEGORY_NAME)
        return mc
    
    @classmethod
    def getInstitute(self, entityId):
        institute = None
        try:
            institute = Institute.objects.get(saml_entityid=entityId)
        except Institute.DoesNotExist:
            self.warning("Insititute IDP %s does not exisit" %(entityId))
        return institute

    @classmethod
    def posixName(self, name):
        if re.search(unsafe_list, name):
            name = re.sub(unsafe_list, "", name.lower())
        return name

    @classmethod
    def parseUserId(self, request):
        dict = {}
        tup = None
        for username in self.username_list:
            dict[username] = username 

        if settings.USER_ID_FILES and settings.USER_ID_DIR:
            filedir = settings.USER_ID_DIR 
            filenames = settings.USER_ID_FILES
            d, error = self.parseMetadata(request)
            if not error:
                username_list = []
                for filename in filenames:
                    if os.path.isfile(filedir + "/" + filename):
                        with open(filedir + "/" + filename) as data:
                            id_list = json.load(data)
                            for ids in id_list:
                                if ids['email'].lower() == d['email'].lower():
                                    if not ids["username"] in dict: 
                                        dict[ids["username"]] = self.posixName(ids["username"])            

        uname = self.getUniqueUsername(d['username'], dict)
        if uname:
            dict[uname] = uname
        udict = self.getUniqueUsernameList(dict)
        if udict:
            tup = tuple(udict.items())
            self.log("Create user id display content")
        return tup
    
    @classmethod
    def formatDefaultProjectPid(self):
        s = string.lowercase
        pid = ''.join(random.sample(s, 2)) + str(random.randint(10, 99))
        return pid

    @classmethod
    def getDefaultProjectPid(self):
        pid = self.formatDefaultProjectPid()
        found = True
        while found:
            try:
                Project.objects.get(pid = pid)
                pid = format_pid()
            except Project.DoesNotExist:
                found = False
        return pid
            
