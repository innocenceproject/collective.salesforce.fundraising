(function($) {
     $(document).ready(function() {
        // Replace the default login form overlay with a custom one that initialized the Janrain widget after load
        $('#portal-personaltools a[href$="/login"], #portal-personaltools a[href$="/login_form"], .discussion a[href$="/login"], .discussion a[href$="/login_form"]').each(function () {
            pb.remove_overlay($(this));
        });
/*
        $('.login-required a.button-create-personal-campaign, #portal-personaltools a[href$="/login"], #portal-personaltools a[href$="/login_form"], .discussion a[href$="/login"], .discussion a[href$="/login_form"]').prepOverlay({
            subtype: 'ajax',
            filter: common_content_filter,
            formselector: 'form#login_form',
            noform: function () {
                if (location.href.search(/pwreset_finish$/) >= 0) {
                    return 'redirect';
                } else {
                    return 'reload';
                }
            },
            redirect: function () {
                var href = location.href;
                if (href.search(/pwreset_finish$/) >= 0) {
                    return href.slice(0, href.length-14) + 'logged_in';
                } else {
                    return href;
                }
            },
            config: {
                onBeforeLoad: function (e) {
                    janrain.engage.signin.widget.init();
                }
            }
        });
*/
        $('.progress-bar').each(function () {
            var percent = $(this).find('span.value').text();
            $(this).reportprogress(percent);
            //$(this).text('');
        });
    
    });
})(jQuery);
