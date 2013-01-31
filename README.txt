Introduction
============

collective.salesforce.fundraising is an online fundraising system designed to help non-profit organizations raise money online.  

The system was initially developed by The Innocence Project, Inc. who sponsored the development with internal staff as well as consulting from Groundwire and design services from Exotic Objects (http://www.exoticobjects.com)

Additional development on personal fundraising and event ticketing was funded by the Innocence Project and jointly developed with Jazkarta (http://www.jazkarta.com).

The first production site is now live at https://secure.innocenceproject.org

In general, the system is currently designed to function as a standalone donation system.  It requires a lot of new packages from Plone and thus may be difficult to integrate into an existing Plone site.

Features
========

*  Self Hosted, PCI SAQ A - A key design requirement was to avoid the cumbersome hosting and process requirements of PCI SAQ C instead preferring the much simpler PCI SAQ A.  PCI SAQ A avoids the requirement for PCI compliant web hosting saving hundreds per month.  The system never touches credit card data, even to receive from the browser and retransmit to an API.  All donation submissions are sent directly to the payment processor.  No credit card data is ever stored or transmitted by your server.

*  Integration with Salesforce Campaigns - Campaigns can be created either in Salesforce or in Plone and are always linked back to a Campaign in Salesforce

*  Campaigns with Timeline and Goal - If a Campaign is configured with a goal (Expected Revenue in Salesforce) and a start/end date (Start/End date in Salesforce), progress indicators in the right column indicate the progress towards the goal and the time remaining to reach the goal.

*  Personal Fundraising - Allow users to create personal campaign pages off any campaign.  Users can set a goal and promote their campaign to their friends.  Personal Campaigns are created as a child Campaign of the main Fundraising Campaign in Salesforce and all donations rollup to the parent campaign in the Hierarchy.

*  Donation Products - "Sell" a selectable quantity of Donation Products in a Fundraising Campaign.  Products can be physical or virtual items or event tickets.  Each products gets its own donation form tab and all donations in Salesforce are linked to the Product.

*  Product Forms - Build a custom donation form through the web with products grouped into fieldsets, optional donation only products (i.e. additionaly donation on ticket purchase), and custom fields mapped back to Salesforce objects (custom fields coming soon).

*  Mailchimp/Mandrill Email Receipts - Use Mailchimp (http://mailchimp.com)  templates to send formatted thank you receipts to donors through the Mandrill (http://mandrill.com) transactional email service.  New templates can be created either in Mailchimp or uploaded directly through the site.  The Mailchimp template is then sync'ed with Mandrill as a template.  The configured templates are then available for selection on each Fundraising Campaign allowing highly stylized receipt emails customized to the campaign.

*  Honorary/Memorial Donations - A checkbox on the donation form allows the user to classify their donation as an Honorary or Memorial donation.  On the next page after submitting the donation, the user can enter the Honorary/Memorial information including optionally sending a notification of their donation via either email (automatically sent by the system) or mail (manually handled through Salesforce)

*  Donor Quotes - After donating, users are prompted to share the campaign or enter a Donor Quote (Testimonial).  Donor Quotes are moderated and once approved are randomly selected for display in a box in the right column

*  Social Integration via Janrain - Janrain is a social login and sharing service.  We've integrated Janrain for social login, mainly used by personal fundraisers, and social sharing to help spread the word about the campaign on multiple social networks

*  Social Share Messages - Inside a campaign, admins can add Share Messages which contain a title, description, image, and default user comment.  On the Share Campaign page, users are presented with 3 randomly selected Share Messages to choose from.  Any donations that come from clicking on a Share Message shared to social networks is tracked back to the Share Message as the Source Campaign.  This allows tracking of the effectiveness of each Share Message

*  Support for one time and recurring donations - The recommended payment processor integration is Stripe (https://stripe.com).  Stripe encodes the credit card data on the client side into a token which can then safely be passed to your server to represent the credit card data.  This approach allows the donation form to post back to your server but without any sensative credit card data in the request.  The Stripe integration is also capable of handling recurring and one time payments through one system.   Previously, one time and recurring donations were handled by Authorize.net Direct Post Method (DPM) for one time and Recurly for recurring.  However, the new integration with Stripe is the recommended payment integration as it is far smoother, free to setup, and less expensive.

*  Sensable site wide defaults with override per campaign - In order to make the process of launching a new campaign as easy and quick as possible, the system stores a site wide configuration for standard fundraising campaigns.  When creating a campaign, you can always override the site defaults for the individual campaign if needed.

*  Configurable "Campaign Seals" per Campaign - A common best practice is to include fundraising "seals" or badges on the donation form to let donors know about third party analysis and endorsements of the organization as well as display charts on the distribution of funds.  Seals can be added by administrators through the web and linked to individual campaigns or sitewide defaults.  Seals contain a compact view with a More Info link to show more details.

*  Simple and Modern UI - Much effort was put into optimizing the user experience to avoid confusing or overwhelming the user while still presenting relevant information at the right time

Installation
============

You can build out a local version of the system using the supplied buildout.cfg file in the root of the package.  Assuming virtualenv for python 2.7.x is in your path already, you should be able to checkout and have a running instance with the following on a Mac (ideally, install libjpeg libraries) or Linux system:

    git clone git@github.com:innocenceproject/collective.salesforce.fundraising.git
    virtualenv --no-site-packages collective.salesforce.fundraising
    cd collective.salesforce.fundraising
    source bin/activate
    python bootstrap.py

    # Run the buildout
    bin/buildout

    # Fire up the instance on port 8080
    bin/instance fg

With a freshly created Plone site, you will want to do the following:
- Install "Fundraising for Salesforce.com" in Add/Remove Products under Site Setup.
- In the ZMI, set the username and password for Salesforce portal_salesforcebaseconnector 
- Go to Fundraising Settings in Site Setup and fill out the form
- Go to Stripe Settings in Add/Remove Products and enter your test and live Stripe keys (https://stripe.com)

Salesforce Setup
================

The system assumes the existence of a number of custom fields in Salesforce.  For now, the following fields will need to be manually created in your Salesforce instance.  In the future, there will be an installable package for Salesforce with the needed customizations.

Opportunity (Donation)
----------------------

Honorary_City__c
Text(128)

Honorary_Contact__c
Lookup(Contact)

Honorary_Country__c
Text(128)

Honorary_Email__c
Email

Honorary_First_Name__c
Text(64)

Honorary_Last_Name__c
Text(64)

Honorary_Message__c
Long Text Area(32768)

Honorary_Notification_Type__c
Picklist

Honorary_Recipient_First_Name__c
Text(64)

Honorary_Recipient_Last_Name__c
Text(64)

Honorary_State__c
Text(128)

Honorary_Street_Address__c
Text(255)

Honorary_Type__c
Picklist

Honorary_Zip__c
Text(32)

Parent_Campaign__c
Lookup(Campaign)

Source_Campaign__c
Lookup(Campaign)

Source_URL__c
URL(255)

Success_Transaction_ID__c
Text(64) (External ID) (Unique Case Insensitive)


OpportunityProduct
------------------

Campaign__c 
*Lookup(Campaign)*

Fundraising_URL__c
*URL(255)*


Contact
-------

Email_Opt_In__c
*Checkbox*

Online_Fundraising_User__c
*Checkbox*


