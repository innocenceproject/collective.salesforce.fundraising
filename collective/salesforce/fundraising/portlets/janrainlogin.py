from urllib import quote
#from zope.interface import alsoProvides
from plone.portlets.interfaces import IPortletDataProvider
#from plone.z3cform.interfaces import IWrappedForm
from zope.interface import implements
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from zope.component.hooks import getSite
#from plone.z3cform.layout import FormWrapper
from collective.pluggablelogin import _
from plone.app.portlets.portlets import base
from plone.app.portlets.portlets import login

#from collective.salesforce.fundraising.forms import SetPasswordForm
#from collective.salesforce.fundraising.forms import AddPersonForm


#class PortletFormWrapper(FormWrapper):
#    index = ViewPageTemplateFile("formwrapper.pt")

class IJanrainLoginPortlet(IPortletDataProvider):
    """A portlet which renders the login form
       along with the Janrain social sign in widget
    """


class Assignment(login.Assignment):
    implements(IJanrainLoginPortlet)

    title = _(u'label_login', default=u'Log In or Register')


class Renderer(login.Renderer):

    render = ViewPageTemplateFile('janrainlogin.pt')

    @property
    def email_login_next_link(self):
        site = getSite()
        url = site.absolute_url() + '/@@email-login-redirect'
        return url

#    @property
#    def set_password_form(self):
#        context = self.context.aq_inner
#
#        # Create a compact version of the contact form
#        # (not all fields visible)
#        form = SetPasswordForm(context, self.request)
#
#        # Wrap a form in Plone view
#        view = PortletFormView(context, self.request)
#        view = view.__of__(context) # Make sure acquisition chain is respected
#        view.form_instance = form
#
#        return view
#
#    @property
#    def add_person_form(self):
#        add_person_form = AddPersonForm(self.context, self.request)
#        alsoProvides(add_person_form, IWrappedForm)
#        return add_person_form.render()


class AddForm(base.NullAddForm):

    def create(self):
        return Assignment()
