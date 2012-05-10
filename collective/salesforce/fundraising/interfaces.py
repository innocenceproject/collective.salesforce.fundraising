from zope.interface import Interface, implements


class IMemberCreated(Interface):
    """Event indicating creation of a member."""


class MemberCreated(object):
    implements(IMemberCreated)

    def __init__(self, member):
        self.member = member
