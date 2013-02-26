import os, random, string
import urllib2
import simplejson
from zope.interface import Interface
from zope.event import notify
from five import grok
from Acquisition import aq_inner
from AccessControl.SecurityManagement import newSecurityManager
from zope.component import getMultiAdapter
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.statusmessages.interfaces import IStatusMessage
from plone.app.layout.viewlets.interfaces import IHtmlHead
from collective.salesforce.fundraising.interfaces import MemberCreated
from collective.salesforce.fundraising.utils import get_settings
from dexterity.membrane.membrane_helpers import get_brains_for_email
from plone.dexterity.utils import createContentInContainer
from zope.app.component.hooks import getSite
from plone.namedfile import NamedBlobImage

JANRAIN_API_BASE_URL = 'https://rpxnow.com/api/v2'

js_template = """<script type="text/javascript">
(function() {
    if (typeof window.janrain !== 'object') window.janrain = {};
    if (typeof window.janrain.settings !== 'object') window.janrain.settings = {};
    
    janrain.settings.tokenUrl = '%(token_url)s';

    function isReady() {
        janrain.ready = true;

        if (janrain.events != null) {        
            janrain.events.onAuthWidgetLoad.addHandler(function () {
                janrain.engage.signin.appendTokenParams({'came_from': '%(came_from)s'});
            });
        }
    };
    if (document.addEventListener) {
      document.addEventListener("DOMContentLoaded", isReady, false);
    } else {
      window.attachEvent('onload', isReady);
    }

    var e = document.createElement('script');
    e.type = 'text/javascript';
    e.id = 'janrainAuthWidget';

    if (document.location.protocol === 'https:') {
      e.src = 'https://rpxnow.com/js/lib/%(site_id)s/engage.js';
    } else {
      e.src = 'http://widget-cdn.rpxnow.com/js/lib/%(site_id)s/engage.js';
    }

    var s = document.getElementsByTagName('script')[0];
    s.parentNode.insertBefore(e, s);


})();
</script>

<script type="text/javascript">
window.onload = function() {
    if (typeof window.janrain !== 'object') window.janrain = {};
    if (typeof window.janrain.settings !== 'object') window.janrain.settings = {};
    if (typeof window.janrain.settings.share !== 'object') window.janrain.settings.share = {};
    if (typeof window.janrain.settings.packages !== 'object') janrain.settings.packages = [];
    janrain.settings.packages.push('share');

    function isReady() { janrain.ready = true; };
    if (document.addEventListener) {
        document.addEventListener("DOMContentLoaded", isReady, false);
    } else {
        window.attachEvent('onload', isReady);
    }

    var e = document.createElement('script');
    e.type = 'text/javascript';
    e.id = 'janrainWidgets';

    if (document.location.protocol === 'https:') {
      e.src = 'https://rpxnow.com/js/lib/%(site_id)s/widget.js';
    } else {
      e.src = 'http://widget-cdn.rpxnow.com/js/lib/%(site_id)s/widget.js';
    }

    var s = document.getElementsByTagName('script')[0];
    s.parentNode.insertBefore(e, s);
};
</script>
"""

SHARE_JS_TEMPLATE = """
  (function ($) {
    $(document).ready(function () {
      $('#%(link_id)s').click(function (e) {
        e.preventDefault();
        e.stopPropagation();
        janrain.engage.share.reset();
        janrain.engage.share.setUrl('%(url)s');
        janrain.engage.share.setTitle('%(title)s');
        janrain.engage.share.setDescription('%(description)s');
        janrain.engage.share.setImage('%(image)s');
        janrain.engage.share.setMessage('%(message)s');
        janrain.engage.share.setActionLink({'name': 'Donate', 'link':'%(url)s'});
        janrain.engage.share.show();
        return false;
      });
    });
  })(jQuery);
"""

def GenPasswd():
    chars = string.ascii_letters + string.digits + '!@#$%^&*()'
    random.seed = (os.urandom(1024))
    return ''.join(random.choice(chars) for i in range(13))
    
class RpxHeadViewlet(grok.Viewlet):
    """ Add the RPX js to the head tag """
   
    grok.name('collective.salesforce.fundraising.janrain.RpxHeadViewlet')
    grok.require('zope2.View')
    grok.context(Interface)
    grok.viewletmanager(IHtmlHead)

    def render(self):
        # Get the site id and app_id from registry
        settings = get_settings()
        janrain_site_id = settings.janrain_site_id
        janrain_sharing_app_id = settings.janrain_sharing_app_id

        if not janrain_site_id:
            return ''

        # Get callback url
        context = aq_inner(self.context)
        portal_state = getMultiAdapter((context, self.request), name=u'plone_portal_state')
        portal_url = portal_state.portal_url()
        token_url = portal_url + '/@@rpx_post_login' 

        # render the js template
        return js_template % {
            'site_id': janrain_site_id, 
            'token_url': token_url,  
            'app_id': janrain_sharing_app_id,  
            'came_from': self.request.get('came_from', self.context.absolute_url()),
        }

class RpxPostLogin(grok.View):
    """ Handle Janrain's POST callback with a token and lookup profile """
    
    grok.name('rpx_post_login')
    grok.context(IPloneSiteRoot)
    grok.require('zope2.View')

    def render(self):
        # Get the api key from registry
        settings = get_settings()
        # workaround for http://bugs.python.org/issue5285, map unicode to strings
        janrain_api_key = str(settings.janrain_api_key)

        if not janrain_api_key:
            return None

        # Get the token
        token = self.request.form.get('token', None)
        if not token:
            return None

        # Get the user profile from Janrain
        auth_info_url = '%s/auth_info?apiKey=%s&token=%s' % (
            JANRAIN_API_BASE_URL,
            janrain_api_key,
            token,
        )
        
        if settings.janrain_use_extended_profile:
            auth_info_url = auth_info_url + '&extended=true'
        
        resp = urllib2.urlopen(auth_info_url)
        auth_info = simplejson.loads(resp.read())

        # This is for Plone's built in member management instead of membrane 
        # See if a user already exists for the profile's email
        #email = auth_info['profile']['email']
        #member = None
        #if email:
            #member = mtool.getMemberById(email)

        # See if user already exists using dexterity.membrane
        profile = auth_info.get('profile',{})

        email = profile.get('verifiedEmail', None)
        if not email:
            email = profile.get('email', None)
        if not email:
            raise AttributeError('No email provided from social profile, unable to create account')

        email = email.lower()

        res = get_brains_for_email(self.context, email, self.request)
        if not res:
            # create new Person if no existing Person was found with the same email
            name = profile.get('name',{})
            address = profile.get('address',{})
            if not address:
                addresses = profile.get('addresses', [])
                if addresses:
                    address = addresses[0]
        
            data = {
                'first_name': name.get('givenName', None),
                'last_name': name.get('familyName', None),
                'email': email,
                'street_address': address.get('streetAddress', None),
                'city': address.get('locality', None),
                'state': address.get('region', None),
                'zip': address.get('postalCode', None),
                'country': address.get('country', None),
                'gender': profile.get('gender', None),
                'social_signin': True,
            }

            # Create the user
            people_container = getattr(getSite(), 'people')
            person = createContentInContainer(
                people_container,
                'collective.salesforce.fundraising.person',
                checkConstraints=False,
                **data
            )

            # Authenticate the user
            mtool = getToolByName(self.context, 'portal_membership')
            acl = getToolByName(self.context, 'acl_users')
            newSecurityManager(None, acl.getUser(email))
            mtool.loginUser()

        # or use the existing Person if found
        else:
            # Authenticate the user
            mtool = getToolByName(self.context, 'portal_membership')
            acl = getToolByName(self.context, 'acl_users')
            newSecurityManager(None, acl.getUser(email))
            mtool.loginUser()

            person = res[0].getObject()

            if person.social_signin == False:
                person.social_signin = True
            
        # Set the photo
        photo = profile.get('photo', None)
        if not photo:
            photos = profile.get('photos',[])
            if photos:
                photo = photos[0]
        if photo and (not person.portrait or not person.portrait.size):
            img_data = urllib2.urlopen(photo).read()
            person.portrait = NamedBlobImage(img_data)

        # See if came_from was passed
        came_from = self.request.form.get('came_from', None)
        # fix odd bug where came_from is a list of two values
        if came_from and isinstance(came_from, (list, tuple)):
            came_from = came_from[0]
            self.request.form['came_from'] = came_from

        # merge in with standard plone login process.  
        login_next = self.context.restrictedTraverse('login_next')

#class RpxXdCommView(grok.View):
#    """ Implement the rpx_xdcomm.html cross domain file """
# 
#    grok.name('rpx_xdcomm.html')
#    grok.context(IPloneSiteRoot)
#    grok.require('zope2.View')

