
from Acquisition import aq_inner
from plone.app.redirector.browser import FourOhFourView
from plone.app.redirector.interfaces import IRedirectionPolicy
from Products.CMFCore.utils import getToolByName
from Products.ZCTextIndex.ParseTree import QueryError, ParseError
from zope.component import getMultiAdapter


_exclude_types = set([
    'collective.salesforce.fundraising.donation',
])


class Custom404View(FourOhFourView):

    def search_for_similar(self):
        path_elements = self._path_elements()
        if not path_elements:
            return None
        path_elements.reverse()
        policy = IRedirectionPolicy(self.context)
        ignore_ids = policy.ignore_ids
        portal_catalog = getToolByName(self.context, "portal_catalog")
        portal_state = getMultiAdapter(
            (aq_inner(self.context), self.request),
            name='plone_portal_state')
        portal_types = [
            t for t in portal_state.friendly_types()
            if t not in _exclude_types]
        navroot = portal_state.navigation_root_path()
        for element in path_elements:
            # Prevent parens being interpreted
            element = element.replace('(', '"("')
            element = element.replace(')', '")"')
            if element not in ignore_ids:
                try:
                    result_set = portal_catalog(
                        SearchableText=element,
                        path=navroot,
                        portal_type=portal_types,
                        sort_limit=10)
                    if result_set:
                        return result_set[:10]
                except (QueryError, ParseError):
                    # ignore if the element can't be parsed as a text query
                    pass
        return []
