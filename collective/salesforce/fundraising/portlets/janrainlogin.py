from urllib import quote
from plone.portlets.interfaces import IPortletDataProvider
from zope.interface import implements
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from zope.site.hooks import getSite

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
    def register_link(self):
        site = getSite()
        url = site.absolute_url() + '/@@register'
        came_from = self.request.form.get('came_from',None)
        if came_from:
            url = url + '?came_from=%s' % quote(came_from)
        return url 

    render = ViewPageTemplateFile('janrainlogin.pt')


class AddForm(base.NullAddForm):

    def create(self):
        return Assignment()
