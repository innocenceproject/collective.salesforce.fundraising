from plone.portlets.interfaces import IPortletDataProvider
from zope.interface import implements
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName

from collective.pluggablelogin import _
from plone.app.portlets.portlets import base
from plone.app.portlets.portlets import login

class IJanrainLoginPortlet(IPortletDataProvider):
    """A portlet which renders the login form
       along with the Janrain social sign in widget
    """


class Assignment(login.Assignment):
    implements(IJanrainLoginPortlet)

    title = _(u'label_login', default=u'Log In')


class Renderer(login.Renderer):

    @property
    def registration_available(self):
        mtool = getToolByName(self.context, 'portal_membership')
        if not mtool.isAnonymousUser():
            return False
        if getToolByName(self.context, 'portal_registration', None) is None:
            return False
        return mtool.checkPermission('Add portal member', self.context)

    @property
    def registration_form(self):
        form = self.context.restrictedTraverse('@@register')
        form.update()
        return form

    render = ViewPageTemplateFile('janrainlogin.pt')


class AddForm(base.NullAddForm):

    def create(self):
        return Assignment()
