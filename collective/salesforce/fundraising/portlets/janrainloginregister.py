from plone.portlets.interfaces import IPortletDataProvider
from zope.interface import implements
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName

from collective.pluggablelogin import _
from plone.app.portlets.portlets import base


class IJanrainLoginRegisterPortlet(IPortletDataProvider):
    """A portlet which renders the registration and login forms
       along with the Janrain social sign in widget
    """


class Assignment(base.Assignment):
    implements(IJanrainLoginRegisterPortlet)

    title = _(u'label_register_or_login', default=u'Register or Log In')


class Renderer(base.Renderer):

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

    @property
    def login_form(self):
        form = self.context.restrictedTraverse('@@login_form')
        form.update()
        return form

    render = ViewPageTemplateFile('janrainloginregister.pt')


class AddForm(base.NullAddForm):

    def create(self):
        return Assignment()
