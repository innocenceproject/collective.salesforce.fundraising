from five import grok
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFCore.utils import getToolByName
from zope.site.hooks import getSite
from Products.PluggableAuthService.interfaces.authservice import IBasicUser
from Products.PluggableAuthService.interfaces.events import IPrincipalCreatedEvent


@grok.subscribe(IBasicUser, IPrincipalCreatedEvent)
def logInNewAccount(user, event):
    # log in user as soon as their account is created
    mtool = getToolByName(getSite(), 'portal_membership')
    if mtool.isAnonymousUser():
        newSecurityManager(None, user)
        mtool.loginUser()
