#!/usr/bin/python

from __future__ import absolute_import
import os, sys, random, string, traceback
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

logger = logging.getLogger(__name__)

class Util(): 

    def __init__(self):
        self.init_file_path = "/root/.karaage_init"

    @classmethod
    def init_file(self):
        return "/root/.karaage_init"

    @classmethod
    def log(self, message):
        logger.debug(message)

    @classmethod
    def init_touch(self):
        with open(self.init_file(), 'a'):
            os.utime(self.init_file(), None)

    @classmethod
    def need_init(self):
        if os.path.isfile(self.init_file()):
            return False 
        return True 
    
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
    def getUsername(self, commonName, lastName):
        firstName = self.getFirstName(commonName, lastName) 
        username = firstName.lower()[0] + lastName[:7].lower()
            
        if self.findUsername(username):
            for i in range(1, 30):
                name = username + str(i)
                if self.findUsername(name) == False:
                    username = name
                    break
        return username

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
    def aafbootstrap(self, request):
        from karaage.institutes.models import Institute
        attr, error_message = self.parseShibAttributes(request)
        new_user = False
        error = False
        if error_message:
            error = True
            return new_user, error 
        d = {}
        d["title"] = ""
        d["first_name"] = attr['first_name']
        d["surname"] = attr['last_name']
        d["full_name"] = attr['full_name']
        d["position"] = ""
        d["department"] = ""
        d["supervisor"] = ""
        d["email"] = attr['email']
        d["username"] = self.getUsername(attr['full_name'], attr['last_name']) 
        d['password'] = self.getPassword()
        d["country"] = ""
        if attr['telephone']:
            d["telephone"] = attr['telephone'] 
        else:
            d["telephone"] = "99029757"
        d["mobile"] = ""
        d["fax"] = ""
        d["address"] = ""
        d["idp"] = attr['idp'] 
        d["short_name"] = attr['last_name'] 
        d['saml_id'] = attr['persistent_id']
        person = self.searchPerson(d["saml_id"])
        if person:
            self.updateProfile(person, d)
        else:
            person = self.addPerson(d)
            if person:
                new_user = True  
        return new_user, error

    @classmethod
    def updateProfile(self, p, d):
        if p.email != d['email']:
            p.email = d['email']
            p.institute = Institute.objects.get(saml_entityid=d['idp'])
            self.log("Update user %s profile" % d['username'])
            p.save()

    @classmethod
    def addPerson(self, d):
        person = None
        try:
            institute = self.getOrCreateDefaultInstitute(d['idp'])
            if not institute:
                return None
            person = Person.objects.create(username = d['username'], password = d['password'], short_name = d['short_name'], full_name = d['full_name'], email = d['email'], institute = Institute.objects.get(saml_entityid = d['idp']), saml_id = d['saml_id'])
            if person:
                if not person.saml_id:
                    person.saml_id = d['saml_id']
                    person.save()
                self.log("Create user account %s" %(person.username))
            if self.need_init():
                self.log("Init projects") 
                if self.setDefaultProjects():
                    self.log("Set default projects OK") 
                    self.init_touch()
                else:
                    self.log("Set default projects failed")
        except:
            self.log("Failed to add person exception %s" % traceback.format_exc())
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
            self.log("Exception to search member in project: %s" % traceback.format_exc())
        return member

    @classmethod
    def getDefaultMachineCategory(self):
        mc = None
        if hasattr(settings, "DEFAULT_MACHINE_CATEGORY_NAME"):
            mc = MachineCategory.objects.get(name = settings.DEFAULT_MACHINE_CATEGORY_NAME)
        return mc
    
    @classmethod
    def getOrCreateDefaultInstitute(self, entityId):
        self.log("getOrCreateDefaultInsitute")
        institute = None
        if hasattr(settings, "DEFAULT_INSTITUTE_NAME"):
            groupname = settings.DEFAULT_INSTITUTE_NAME
            try:
                group, _ =Group.objects.get_or_create(name = groupname)
#                institute = Institute.objects.get(saml_entityid=entityId, name = groupname)
                institute = Institute.objects.get(name = groupname)
                
            except Institute.DoesNotExist:
                institute = Institute(name = groupname, group = group, saml_entityid = entityId, is_active = True)
                if institute:
                    institute.save()
        return institute

    @classmethod
    def getProject(self, name):
        self.log("Get Project 1 %s" %(name))
        project = None
        try:
            project = Project.objects.get(name = name)
            if project:
                self.log("Find project %s" %(project.name))
            else:
                self.log("Project %s not found" %(project.name))
        except Project.DoesNotExist:
            self.log("project %s does not exists" %(name))
        except:
            self.log("Exception: ", traceback.format_exc())
        finally:
            return project

    @classmethod
    def createProject(self, pid, name, institute_name):
        project = None
        try:
            institute = getInstitute(institute_name)
            if institute:
                self.log("Find insititute %s" %(institute.name))
                project = Project.objects.create(pid = pid, name = name, institute = institute)
            else:
                self.log("Insititute %s does not exist" %(institute_name))
        except:
            self.log("Exception: ", traceback.format_exc())
        finally:
            return project

    @classmethod
    def setDefaultProjects(self):
        result = True 
        if hasattr(settings, "DEFAULT_PROJECTS"):
            for p in settings.DEFAULT_PROJECTS:
                project = self.getProject(p["project_name"])
                if project:
                    self.log("Find project %s" %(project.name))
                else:
                    self.log("Create project name = %s, pid = %s, institute name = %s" %(p["project_name"], p["pid"], p["institute_name"]))
                    project = self.createProject(p["pid"], p["project_name"], p["institute_name"])
                    if project:
                        self.log("Create project %s OK." %(project.name))
                    else:
        		result = False
                        self.log("Create project %s failed." %(p["project_name"]))
                        break
        return result            

