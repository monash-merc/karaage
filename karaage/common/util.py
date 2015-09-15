#!/usr/bin/python

from __future__ import absolute_import
import os, sys, random, string, traceback, datetime
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

    def __init(self):
        projectId = "pCvl"

    @classmethod
    def log(self, message):
        logger.debug(message)

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
            return new_user, error, None 
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
        return new_user, error, person 

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
    def getInstitute(self, entityId):
        institute = None
        try:
            institute = Institute.objects.get(saml_entityid=entityId)
        except Institute.DoesNotExist:
            self.log("Insititute IDP %s does not exisit" %(entityId))
        return institute

            

