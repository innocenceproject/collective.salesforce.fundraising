import os, random, string
import urllib2
import simplejson
from zope.interface import Interface
from zope.component import getUtility
from zope.event import notify
from five import grok
from Acquisition import aq_inner
from AccessControl.SecurityManagement import newSecurityManager
from zope.component import getMultiAdapter
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.statusmessages.interfaces import IStatusMessage
from plone.app.layout.viewlets.interfaces import IHtmlHead
from plone.registry.interfaces import IRegistry
from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings
from collective.salesforce.fundraising.interfaces import MemberCreated

JANRAIN_API_BASE_URL = 'https://rpxnow.com/api/v2'

js_template = """<script type="text/javascript">
(function() {
    if (typeof window.janrain !== 'object') window.janrain = {};
    if (typeof window.janrain.settings !== 'object') window.janrain.settings = {};
    
    janrain.settings.tokenUrl = '%(token_url)s';

    function isReady() {
        janrain.ready = true;
        
        janrain.events.onAuthWidgetLoad.addHandler(function () {
            janrain.engage.signin.appendTokenParams({'came_from': '%(came_from)s'});
        });
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
    var rpxJsHost = (("https:" == document.location.protocol) ? "https://" : "http://static.");
    document.write(unescape("%%3Cscript src='" + rpxJsHost + "rpxnow.com/js/lib/rpx.js' type='text/javascript'%%3E%%3C/script%%3E"));
</script>

<script type="text/javascript"><!--
    function rpxShareButton (rpxButtonTarget, rpxLabel, rpxSummary, rpxLink, rpxLinkText, rpxComment, rpxImageSrc){
        RPXNOW.init({appId: '%(app_id)s', xdReceiver: '/rpx_xdcomm.html'});
        rpxButtonTarget.click(function () {
            RPXNOW.loadAndRun(['Social'], function () {
                var activity = new RPXNOW.Social.Activity(
                rpxLabel,
                rpxLinkText,
                rpxLink);
                activity.setUserGeneratedContent(rpxComment);
                activity.setDescription(rpxSummary);
                activity.addActionLink('Donate', '%(came_from)s');
                if (rpxImageSrc.length > 0) {
                    if (document.getElementById('rpxshareimg') != undefined && (rpxImageSrc == '' || rpxImageSrc == null)) {
                        rpxImageSrc = document.getElementById('rpxshareimg').src;
                    }
                    if (rpxImageSrc != '' && rpxImageSrc != null) {
                        var shareImage = new RPXNOW.Social.ImageMediaCollection();
                        shareImage.addImage(rpxImageSrc,rpxLink);
                        activity.setMediaItem(shareImage);
                    }
                }
                
                RPXNOW.Social.publishActivity(activity,
                    {finishCallback:function(data){
                        for (i in data) {
                            if (data[i].success == true) {
                                //do something for each share success here
                                //e.g. recordShare(data[i].provider_name, data[i].provider_activity_url);
                            }
                        }
                    }
                });
            });
            return false;
        });
    }

    
--></script>
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
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFundraisingSettings)
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
            'came_from': self.context.absolute_url(),
        }

class RpxPostLogin(grok.View):
    """ Handle Janrain's POST callback with a token and lookup profile """
    
    grok.name('rpx_post_login')
    grok.context(IPloneSiteRoot)
    grok.require('zope2.View')

    def render(self):
        # Get the api key from registry
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFundraisingSettings)
        janrain_api_key = settings.janrain_api_key

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
        
        resp = urllib2.urlopen(auth_info_url)
        auth_info = simplejson.loads(resp.read())

    
        # See if a user already exists for the profile's email
        mtool = getToolByName(self.context, 'portal_membership')
        email = auth_info['profile']['email']
        member = None
        if email:
            member = mtool.getMemberById(email)
       
        # If no user exists, create one
        if member:
            # Authenticate the user
            newSecurityManager(None, member.getUser())
            mtool.loginUser()    

        else:
            # Create the member
            rtool = getToolByName(self.context, 'portal_registration')
            member = rtool.addMember(
                email, 
                GenPasswd(), 
                properties={
                    'username': email.lower(),
                    'fullname': auth_info['profile']['name']['formatted'], 
                    'email': email.lower(),
                },
            )

            # Raise the MemberCreated event to trigger SF sync and 
            # auto log the user in
            notify(MemberCreated(member))  

        # Set a status message informing the user they are logged in
        IStatusMessage(self.request).add(u'You are now logged in.')
        
        # See if came_from was passed
        came_from = self.request.form.get('came_from', None)
        if came_from:
            # For some reason, came_from is getting passed twice by Janrain
            #return self.request.RESPONSE.redirect(came_from)
            return self.request.RESPONSE.redirect(came_from[0])

        # Redirect
        return self.request.RESPONSE.redirect(self.context.absolute_url())

class RpxXdCommView(grok.View):
    """ Implement the rpx_xdcomm.html cross domain file """
 
    grok.name('rpx_xdcomm.html')
    grok.context(IPloneSiteRoot)
    grok.require('zope2.View')

