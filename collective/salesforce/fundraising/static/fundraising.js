var _GET_VARS = {};

document.location.search.replace(/\??(?:([^=]+)=([^&]*)&?)/g, function () {
    function decode(s) {
        return decodeURIComponent(s.split("+").join(" "));
    }

    _GET_VARS[decode(arguments[1])] = decode(arguments[2]);
});

/*! http://mths.be/placeholder v1.8.7 by @mathias */
(function(f,h,c){var a='placeholder' in h.createElement('input'),d='placeholder' in h.createElement('textarea'),i=c.fn,j;if(a&&d){j=i.placeholder=function(){return this};j.input=j.textarea=true}else{j=i.placeholder=function(){return this.filter((a?'textarea':':input')+'[placeholder]').not('.placeholder').bind('focus.placeholder',b).bind('blur.placeholder',e).trigger('blur.placeholder').end()};j.input=a;j.textarea=d;c(function(){c(h).delegate('form','submit.placeholder',function(){var k=c('.placeholder',this).each(b);setTimeout(function(){k.each(e)},10)})});c(f).bind('unload.placeholder',function(){c('.placeholder').val('')})}function g(l){var k={},m=/^jQuery\d+$/;c.each(l.attributes,function(o,n){if(n.specified&&!m.test(n.name)){k[n.name]=n.value}});return k}function b(){var k=c(this);if(k.val()===k.attr('placeholder')&&k.hasClass('placeholder')){if(k.data('placeholder-password')){k.hide().next().show().focus().attr('id',k.removeAttr('id').data('placeholder-id'))}else{k.val('').removeClass('placeholder')}}}function e(){var o,n=c(this),k=n,m=this.id;if(n.val()===''){if(n.is(':password')){if(!n.data('placeholder-textinput')){try{o=n.clone().attr({type:'text'})}catch(l){o=c('<input>').attr(c.extend(g(this),{type:'text'}))}o.removeAttr('name').data('placeholder-password',true).data('placeholder-id',m).bind('focus.placeholder',b);n.data('placeholder-textinput',o).data('placeholder-id',m).before(o)}n=n.removeAttr('id').hide().prev().attr('id',m).show()}n.addClass('placeholder').val(n.attr('placeholder'))}else{n.removeClass('placeholder')}}}(this,document,jQuery));

function form_input_is_int(input){
  return !isNaN(input)&&parseInt(input)==input;
}

function setupRecurlyForm() {
    // Do some mangling of the Recurly form to fit the same general form structure
    var recurly_form = jQuery('#recurly-subscribe');
    
    if (recurly_form.length == 0) {
        return false;
    }

    var address = recurly_form.find('div.address');
    var accepted_cards = recurly_form.find('div.accepted_cards');
    var names = recurly_form.find('.credit_card div.first_name, .credit_card div.last_name');
    var card_cvv = recurly_form.find('div.card_cvv');

    card_cvv.before(accepted_cards);
    names.wrapAll('<div class="field compound name"></div>');

    var button_submit = recurly_form.find('button.submit');
    button_submit.text('Submit').after('<div class="discreet">Your card will be automatically charged every month</div>');
}

(function ($) {

// Donation form logic
function showHideDonationForm(form) {
    var min_value = 5;
    if (form.hasClass('donation-form-product') == true) {
        min_value = 1;
    }
    var amount = form.find('.field-amount input[name="x_amount"]').val();

    if (amount >= min_value) {
        form.parents('div.panel').find('.after-amount').slideDown();
    } else {
        form.parents('div.panel').find('.after-amount').slideUp();
    }
}

function processNewAmountValue() {
    var options = $(this).parents('.field').find('.options');
    var form = options.parents('form');

    if (form.hasClass('donation-form-product') == true) {
        updateDonationProductTotal(form);
    }

    options.find('.option').removeClass('selected');
    var option = options.find('input[value="' + $(this).val() + '"]');
    option.parent('.option').addClass('selected');

    showHideDonationForm(form)

    // Recurly integration
    if (form.hasClass('donation-form-recurly') == true) {
        populateRecurlyQuantity($(this).val());
    }

    // Authorize.net DPM integration
    if (form.hasClass('donation-form-authnet-dpm') == true) {
        updateAuthnetDpmFingerprint(form);
    }

}

function updateDonationProductTotal(form) {
    var quantity = form.find('input[name="c_quantity"]').val();
    var price = form.find('.product-price .value').text();
    var total = quantity * price;
    form.find('input[name="x_amount"]').val(total);
}

function updateProductFormTotal(form) {
    var new_total = 0;

    form.find('input.field-product-quantity').each(function () {
        var field = $(this);
        if (field.val() != null && field.val() > 0) {
            var price = field.parent().find('.hidden-price').text();
            if (price != null && price > 0) {
                var subtotal = price * field.val();
                new_total = new_total + subtotal;
            }
        }
    });
    form.find('input[name="x_amount"]').val(new_total);
    updateAuthnetDpmFingerprint(form);
    populateAuthnetDescription(form);
    
    if (new_total > 0) {
        form.find('a.button-checkout').addClass('available');
    } else {
        form.find('a.button-checkout').removeClass('available');
    }
}

function updateProductFormItems(form) {
    var products_field = form.find('input[name="c_products"]');
    var products = [];
     
    form.find('input.field-product-quantity').each(function () {
        var field = $(this);
        if (field.val() != null && field.val() > 0) {
            var sf_id = field.attr('id').replace('donationform-field-','');
            var product = sf_id + ':' + field.val();
            products.push(product);
        }
    });
    
    products_field.val(products.join(','));
}

function updateAuthnetDpmFingerprint(form) {
    if (! form.hasClass('donation-form-authnet-dpm')) {
        return;
    }
    
    var fingerprint_url = form.find('#authnet_dpm_fingerprint_url').val();
    fingerprint_url = fingerprint_url + '?amount='+ form.find('input[name="x_amount"]').val() +'&sequence='+form.find('input[name="x_fp_sequence"]').val()
    
    $.get(fingerprint_url, function (data) {
        $('.donation-form-authnet-dpm input[name="x_fp_hash"]').val(data.x_fp_hash);
        $('.donation-form-authnet-dpm input[name="x_fp_timestamp"]').val(data.x_fp_timestamp);
    }, 'json');
}

function populateRecurlyQuantity(amount) {
    // If there is a Recurly form on the page, set the quantity to amount
    var form = $('#recurly-subscribe form');
    if (form.length != 0) {
        form.find('.field.quantity input').val(amount);
    }
}

function setupAuthnetDpmForm() {
    var forms = $('form.donation-form-authnet-dpm');
    forms.each(function () {
        var form = $(this);
        if (form.length == 0) {
            return;
        }
    
        // Turn off AJAX request caching to ensure a stale fingerprint doesn't get cached
        $.ajaxSetup({ cache: false });
    
        // Concatenate expiration month/year
        var exp_month = form.find('select.card-expiration-month');
        var exp_year = form.find('select.card-expiration-year');
        var exp_full = form.find('input[name="x_exp_date"]');
        exp_full.val(exp_month.val() + exp_year.val());
        exp_month.change(function () {
            exp_full.val(exp_month.val() + exp_year.val());
        })
        exp_year.change(function () {
            exp_full.val(exp_month.val() + exp_year.val());
        })
    
        // Setup populate of Authorize.net transaction description field
        var first_name = form.find("input[name='x_first_name']").change(populateAuthnetDescription);
        var last_name = form.find("input[name='x_last_name']").change(populateAuthnetDescription);
        var amount = form.find("input[name='x_amount']").change(populateAuthnetDescription);
        var description = form.find("input[name='x_description']").change(populateAuthnetDescription);
    
        // Require integer in account field
        amount.change(function () {
            if (form_input_is_int($(this).val()) == false) {
                alert('Please enter a whole number for the Amount');
            }
        });
    
        // Setup the authnet dpm fingerprint to refresh every 10 minutes
        var fingerprintRefresh = setInterval(function () {
            updateAuthnetDpmFingerprint(form);
        }, 600000);
    });
}

function hideDonationErrorOnChange(form) {
    form.find('input, select').change(function () {
        $('.field-error-message').slideUp(function () {$(this).remove()});
        form.find('.donation-form-error').slideUp();
    });
}

function clearFormSubmit(form) {
    form.find('.form-buttons .button-loading-indicator').hide();
    var buttons = form.find('.form-buttons input');
    buttons.removeClass('submitted');
    buttons.removeClass('submitting');
    buttons.attr('disabled', false);
}

function stripeDonationResponseHandler(status, response) {
    // FIXME: This handler will currently only work with a single Stripe donation form on the page
    //        Need to determine how to determine the originating form somehow (perhaps class on form before token generation?)
    if (response.error) {
        var form = $('.donation-form-stripe').eq(0);
        // Show the errors on the form
        var form_error = form.find('.donation-form-error');
        if (response.error.message.length > 0) {
            form_error.find('h5').text('There was an issue processing your gift');
            form_error.find('p.error-message').text(response.error.message);
            form_error.slideDown();
            hideDonationErrorOnChange(form);
        }
        clearFormSubmit(form);

        // FIXME: this didn't work for some reason, possibly jquery version issues?
        //$('.form-buttons input').prop('disabled', false);
    } else {
        var form = $('.donation-form-stripe');
        // token contains id, last4, and card type
        var token = response.id;
        // Insert the token into the form so it gets submitted to the server
        form.append($('<input type="hidden" name="stripeToken" />').val(token));

        $.ajax({
            url: form.attr('action'), 
            data: form.serializeArray(), 
            type: 'POST',
            success: function (data, textStatus) {
                if (data['success'] == true) {
                    window.location = data['redirect'];
                    return false;
                } else {
                    var form = $('.donation-form-stripe').eq(0);
                    var form_error = form.find('.donation-form-error');
                    $('html, body').animate({ scrollTop: form_error.prev().offset().top - $('body').offset().top});
                    form_error.find('h5').text('There was an issue processing your gift');
                    form_error.find('p.error-message').text(data['message']);
                    form_error.slideDown();
                    hideDonationErrorOnChange(form);
                    clearFormSubmit(form);
                }
            },
            error: function (data, textStatus) {
                var form = $('.donation-form-stripe').eq(0);
                var form_error = form.find('.donation-form-error');
                $('html, body').animate({ scrollTop: form_error.prev().offset().top - $('body').offset().top});
                form_error.find('h5').text('There was an issue processing your gift');
                form_error.find('p.error-message').text('Please try again or contact us for assistance');
                form_error.slideDown();
                hideDonationErrorOnChange(form);
                clearFormSubmit(form);
            },
            dataType: 'json'
        });
    }
}

function setupStripeForm() {
    var forms = $('form.donation-form-stripe');
    forms.each(function () {
        var stripe_form = $(this);
        
        //stripe_form.submit(stripPlaceholderValues);

        stripe_form.data('validator').onSuccess = function () {
            var stripe_form = $(this);
            if (stripe_form.checkValidity() == true) {
                Stripe.createToken({
                    number: stripe_form.find('.subfield-card-number input').val(),
                    name: stripe_form.find('.subfield-first-name input').val() + ' ' + stripe_form.find('.subfield-last-name input').val(),
                    cvc: stripe_form.find('.subfield-card-cvc input').val(),
                    exp_month: stripe_form.find('select.card-expiration-month').val(),
                    exp_year: stripe_form.find('select.card-expiration-year').val(),
                    address_line1: stripe_form.find('.subfield-address input').val(),
                    address_city: stripe_form.find('.subfield-city input').val(),
                    address_state: stripe_form.find('.subfield-state input').val(),
                    address_zip: stripe_form.find('.subfield-zip input').val(),
                    address_country: stripe_form.find('.subfield-country input').val()
                }, stripeDonationResponseHandler);
            }
            //return false;
        };

        stripe_form.submit(function (e) {
            e.preventDefault();
            return false;
        });
    })
}

function handleHonoraryTypeChange() {
    var form = $(this).parents('form.donation-form-honorary');
    if ($(this).attr('checked') == true) {
        var honorary_name = form.find('.field-honorary-name')
        var honorary_name_label = honorary_name.find('label')
        if ($(this).val() == 'Memorial') {
            honorary_name_label.text(honorary_name_label.text().replace('honor','memory'));
            form.find('.field.honorary-recipient').show();
        }
        if ($(this).val() == 'Honorary') {
            honorary_name_label.text(honorary_name_label.text().replace('memory','honor'));
            form.find('.field.honorary-recipient').hide();
        }
        honorary_name.slideDown();
        form.find('.field-honorary-send, .fieldset-notification').slideDown();
        form.find('.fieldset-preview').slideDown();
        
        form.find('.form-buttons').slideDown();
    }
    refreshHonoraryPreview(form);
}

function handleHonoraryNotificationChange() {
    var form = $(this).parents('form.donation-form-honorary');

    if ($(this).attr('checked') == true) {
        var recipient = form.find('.field-recipient');
        var email = form.find('.field-email');
        var address = form.find('.field-address');
        var message = form.find('.fieldset-message');
        var preview = form.find('.fieldset-preview');

        message.find('.field').show();

        if ($(this).val() == 'Email') {
            recipient.show();
            email.show();
            address.hide();
            recipient.find('input[name]').attr('required','required');
            email.find('input[name]').attr('required', 'required');
            address.find('input[name], select[name]').removeAttr('required');
            message.show();
            preview.show();
            //return false;
        } 
        if ($(this).val() == 'Mail') {
            recipient.show();
            email.hide();
            address.show();
            recipient.find('input[name]').attr('required','required');
            email.find('input[name]').removeAttr('required');
            address.find('input[name], select[name]').attr('required', 'required');
            message.show();
            preview.show();
            //return false;
        } 
        if ($(this).val() == 'None' || $(this).val() == '') {
            recipient.hide();
            message.hide();
            email.hide();
            address.hide();
            recipient.find('input[name]').removeAttr('required');
            email.find('input[name]').removeAttr('required');
            address.find('input[name], select[name]').removeAttr('required');
            preview.hide();
        }

        refreshHonoraryPreview(form);
    }
}

function handleHonoraryShowAmountChange() {
    var form = $(this).parents('form.donation-form-honorary');
    refreshHonoraryPreview(form);
}

function refreshHonoraryPreview(form) {
    var preview_fieldset = form.find('.fieldset-preview');
    var honorary_notification_type = form.find('input[name="honorary_notification_type"]:checked').val();

    if (honorary_notification_type == 'None' || honorary_notification_type == '') {
        preview_fieldset.slideUp();
        return;
    }

    var honorary_type = form.find('input[name="honorary_type"]:checked').val();

    var show_amount = form.find('input[name="show_amount"]:checked').val();

    var preview_href = '';
    if (honorary_type == 'Honorary') {
        if (show_amount == 'Yes') {
            preview_href = preview_fieldset.find('.preview-links a.honorary-preview-with-amount').attr('href');
        } else {
            preview_href = preview_fieldset.find('.preview-links a.honorary-preview-without-amount').attr('href');
        }
    }

    if (honorary_type == 'Memorial') {
        if (show_amount == 'Yes') {
            preview_href = preview_fieldset.find('.preview-links a.memorial-preview-with-amount').attr('href');
        } else {
            preview_href = preview_fieldset.find('.preview-links a.memorial-preview-without-amount').attr('href');
        }
    }

    if (preview_href == '') {
        return false;
    }

    preview_fieldset.find('.field-preview').load(preview_href, function () {$(this).slideDown()});
}

function linkStateAndCountryField() {
    var value = $(this).val();
    var field = $(this).parents('.field');
    var state_select = field.find('.subfield-state select');
    var state_input = field.find('.subfield-state input');
    var state_field_name = state_select.attr('name');
    if (state_field_name == '') {
        state_field_name = state_input.attr('name');
    }

    if (value == 'US') {
        state_select.attr('name', state_field_name).attr('required', 'required').show();
        state_input.attr('name', '').removeAttr('required').hide();
    } else {
        state_select.attr('name', '').removeAttr('required').hide();
        state_input.attr('name', state_field_name).show();
    }
}

function setupHonoraryForm() {
    var form = $('form.donation-form-honorary');

    if (form.length == 0) {
        return;
    }

    // Handle changes in the type
    var type_input = form.find('.field-honorary-type .option input');
    type_input.change(handleHonoraryTypeChange);
    type_input.change();

    // Handle changes in send
    var send_input = form.find('.field-honorary-send .option input');
    send_input.change(handleHonoraryNotificationChange);
    send_input.change();
    
    // Handle changes in show_amount
    var send_input = form.find('.subfield-show-amount .option input');
    send_input.change(handleHonoraryShowAmountChange);
    send_input.change();
    
}

function setupProductForm() {
    var form = $('form.donation-form.product-form');
    
    if (form.length == 0) {
        return;
    }

    // Handle changes in quantity
    form.find('input.field-product-quantity').each(function () {
        $(this).keyup(function () {updateProductFormTotal(form)});
        $(this).change(function () {updateProductFormTotal(form)});
        $(this).keyup(function () {updateProductFormItems(form)});
        $(this).change(function () {updateProductFormItems(form)});
    });

    // Wire up the checkout button
    form.find('a.button-checkout').click(function (e) {
        showHideDonationForm(form);
        e.preventDefault();
        return false;
    });
    form.find('.edit-links a').prepOverlay({subtype: 'iframe', config: {onClose: function() { location.reload(); }}});

    // Handle collapsed fieldsets
    form.find('.product-fieldset.collapsed .expand-link a').click(function () {
        var fieldset = $(this).closest('.product-fieldset.collapsed');
        $(this).slideUp();
        fieldset.find('.product-fieldset-contents').slideDown(function () {fieldset.removeClass('collapsed')});
        return false;
    });
}

function populateAuthnetDescription() {
    var field = $(this);
    var form = field.parents('form.donation-form-authnet-dpm');
    var amount_txt = form.find("input[name='x_amount']").val()

    // If this is a product, put the product and quantity name in amount_txt instead of amount
    if (form.hasClass('donation-form-product') == true) {
        var product_name = form.find('.field-amount .product-name').text();
        var quantity = form.find("input[name='c_quantity']").val();
        amount_txt = quantity + ' ' + product_name;
    }

    // we could serialize, but then our javascript touches the cc info
    var first_name = form.find("input[name='x_first_name']").val()
    var last_name = form.find("input[name='x_last_name']").val()
    var description = first_name + ' ' + last_name + ' - $' + amount_txt + ' Donation';
    form.find("input[name='x_description']").val(description);
}

function stripPlaceholderValues() {
    // If value = placeholder, remove value on submit
    $(this).find('input[type=text], input[type=email]').each(function () {
        if ($(this).attr('placeholder') && $(this).val() == $(this).attr('placeholder')) {
            $(this).val('');
        }    
    });
}

function stripFormPlaceholderValues(form) {
    // If value = placeholder, remove value on submit
    form.find('input[type=text], input[type=email]').each(function () {
        if (form.attr('placeholder') && form.val() == form.attr('placeholder')) {
            form.val('');
        }    
    });
}

/* calculate error message position relative to the input */    
// Pulled directly from jquerytools for use in custom effect below
function getPosition(trigger, el, conf) {
    
    // Get the first element in the selector set
    el = $(el).first() || el;
    
    // get origin top/left position 
    var top = trigger.offset().top,
        left = trigger.offset().left,
        pos = conf.position.split(/,?\s+/),
        y = pos[0],
        x = pos[1];
    
    top  -= el.outerHeight() - conf.offset[0];
    left += trigger.outerWidth() + conf.offset[1];
    
    
    // iPad position fix
    if (/iPad/i.test(navigator.userAgent)) {
        top -= $(window).scrollTop();
    }
    
    // adjust Y     
    var height = el.outerHeight() + trigger.outerHeight();
    if (y == 'center')  { top += height / 2; }
    if (y == 'bottom')  { top += height; }
    
    // adjust X
    var width = trigger.outerWidth();
    if (x == 'center')  { left -= (width  + el.outerWidth()) / 2; }
    if (x == 'left')    { left -= width; }   
    
    return {top: top, left: left};
}

$(document).ready(function() {
    // Replace the default login form overlay with a custom one that initialized the Janrain widget after load
    $('#portal-personaltools a[href$="/login"], #portal-personaltools a[href$="/login_form"], .discussion a[href$="/login"], .discussion a[href$="/login_form"]').each(function () {
        pb.remove_overlay($(this));
    });

    $('.progress-bar').each(function () {
        var percent = $(this).find('span.value').text();
        $(this).reportprogress(percent);
        //$(this).text('');
    });

    // HTML5 placeholder attribute processing in non-HTML5 browsers
    //function placeholder(){
    //    $("form.donation-form input[type=text], form.donation-form input[type=email]").each(function(){
    //        var phvalue = $(this).attr("placeholder");
    //        if ($(this).val() == '') {
    //            $(this).val(phvalue);
    //            $(this).addClass('placeholder');
    //        }
    //    });
    //}
    //placeholder();
    //$("form.donation-form input[type=text], form.donation-form input[type=email]").focusin(function(){
    //    var phvalue = $(this).attr("placeholder");
    //    if (phvalue == $(this).val()) {
    //        $(this).val("");
    //        $(this).removeClass('placeholder');
    //    }
    //});
    //$("form.donation-form input[type=text], form.donation-form input[type=email]").focusout(function(){
    //    var phvalue = $(this).attr("placeholder");
    //    if ($(this).val() == "") {
    //        $(this).val(phvalue);
    //        $(this).addClass('placeholder');
    //    }
    //});
    //$("form.donation-form input[type=text], form.donation-form input[type=email]").keyup(function(){
    //    if ($(this).val() != '') {
    //        $(this).removeClass('placeholder');
    //    }
    //});
    
    // adds an effect called "scrolltofield" to the validator
    $.tools.validator.addEffect("scrolltofield", function(errs, event) {
        var conf = this.getConf();
        var err_fields = [];

        // loop errors
        $.each(errs, function(i, err) {
  
            // add error class  
            var input = err.input;                  
            input.addClass(conf.errorClass);
            
            // add to err_fields
            err_fields.push(input.attr('name'))
         
            // If single error is enabled, focus on the input
            if (conf.singleError == true) {
                var buttons = input.parents('form').find('.form-buttons');
                buttons.find('.field-error-message').remove();
                buttons.append('<div class="field-error-message"><p>Please fix the errors shown above</p></div>');
                setInterval(function () {
                    buttons.find('.field-error-message').slideUp().remove();
                }, 5000);
                if ($.browser.msie != true) {
                    var container = $('body');
                    container.animate({scrollTop: input.offset().top - container.offset().top});
                }
            }
                
            // get handle to the error container
            var msg = input.data("msg.el"); 
            
            // create it if not present
            if (!msg) { 
                msg = $(conf.message).addClass(conf.messageClass).appendTo(document.body);
                input.data("msg.el", msg);
            }  
            
            // clear the container 
            msg.css({visibility: 'hidden'}).find("p").remove();
            
            // populate messages
            $.each(err.messages, function(i, m) { 
                $("<p/>").html(m).appendTo(msg);            
            });
            
            // make sure the width is not full body width so it can be positioned correctly
            if (msg.outerWidth() == msg.parent().width()) {
                msg.add(msg.find("p")).css({display: 'inline'});        
            } 
            
            // insert into correct position (relative to the field)
            var pos = getPosition(input, msg, conf); 
             
            msg.css({ visibility: 'visible', position: 'absolute', top: pos.top, left: pos.left })
                .fadeIn(conf.speed);     
   
            // Clear submitting and submitted classes to allow re-submission
            clearFormSubmit(input.closest('form'));

            if (conf.singleError == true) {
                return false;
            }
        });
        
    }, function (inputs) {});
 
    // Setup donation form tabs
    $('.donation-form-wrapper ul.tabs').tabs('.donation-form-wrapper .panels > .panel');
    // Show panels with no tabs (the template skips rendering tabs if there is only one)
    $('.panels').not('ul.tabs ~ .panels').find('.panel').show();

   
    // Setup donation level buttons 
    $('.field-donation-amount .option label').click(function () {
        var radio = $(this).parent().find('input');
        var option = radio.parents('.option');
        var options = option.parents('.options');
        var field = options.parents('.field:first');
        var form = field.parents('form:first');
        var amount_field = form.find('.field-amount input');

        // If this is a donation product form, swap quantity field for amount field
        if (form.hasClass('donation-form-product') == true) {
            amount_field = form.find('.field-quantity input');
        }

        amount_field.val(radio.val());
        options.find('.option').removeClass('selected');
        option.addClass('selected');
        showHideDonationForm(form);
        populateRecurlyQuantity(radio.val());

        if (form.hasClass('donation-form-product') == true) {
            updateDonationProductTotal(form);
        }

        updateAuthnetDpmFingerprint(form);

    });

    // Construct Authorize.net transaction description as inputs change
    //var authnet_dpm_form = ($('.donation-form-authnet-dpm').length);
    //if (authnet_dpm_form.length) {
    //}

    $('form.donation-form').each(function () {
        var form = $(this);
        var handle_form = true;
        showHideDonationForm(form);

        // If this is not a recurly form (which already handles client side validation), enable validation
        if (form.hasClass('donation-form-recurly') == true) {
            handle_form = false;
        }

        if (form.hasClass('donation-form-honorary') == true) {
            handle_form = false;
        }

        if (handle_form == true) {
            // Setup placeholders
            form.find('input, textarea').placeholder();

            // Set validator
            form.attr('novalidate','novalidate');
            form.validator({
                //effect: 'scrolltofield', 
                singleError: true, 
                position: 'bottom left', 
                errorInputEvent: 'keyup',
                //inputEvent: 'blur',
                messageClass: 'field-error-message', 
                onFail: function (e, els) {
                    clearFormSubmit(form);
                }
            // Handle form submit
            }).submit(function(e) {
                var form = $(this);
    
                // client-side validation passed
                if (!e.isDefaultPrevented()) {
                    // Mark the form as submitted
                    var button = form.find('.form-buttons input');
                    button.attr('disabled', true);
                    //button.addClass('submitted');
                    button.addClass('submitting');
                    button.next('.button-loading-indicator').show();
    
                    // For Authorize.net DPM method, just submit the form normally
                    if (form.hasClass('donation-form-authnet-dpm') == true) {
                        return;
                    }
    
                    // For Stripe, create the token and trigger the response handler
                    if (form.hasClass('donation-form-stripe') == true) {
                        Stripe.createToken({
                            number: form.find('.subfield-card-number input').val(),
                            name: form.find('.subfield-first-name input').val() + ' ' + form.find('.subfield-last-name input').val(),
                            cvc: form.find('.subfield-card-cvc input').val(),
                            exp_month: form.find('select.card-expiration-month').val(),
                            exp_year: form.find('select.card-expiration-year').val(),
                            address_line1: form.find('.subfield-address input').val(),
                            address_city: form.find('.subfield-city input').val(),
                            address_state: form.find('.subfield-state input').val(),
                            address_zip: form.find('.subfield-zip input').val(),
                            address_country: form.find('.subfield-country input').val()
                        }, stripeDonationResponseHandler);
                    }
                }

                // prevent default form submission logic
                e.preventDefault();
            });
        }
    });

    $('.field-donation-amount .field-amount').each(function () {
        var input = $(this).find('input');
        if ($(this).parents('form.donation-form-product').length > 0) {
            // Bind to the quantity field for a product
            input = $(this).find('.field-quantity input');
        }
        input.change(processNewAmountValue);
        input.keyup(processNewAmountValue);
    });

    //$("form").validationEngine('attach');

    setupAuthnetDpmForm();
    setupHonoraryForm();
    //setupStripeForm();
    setupProductForm();

    // Handle Fundraising Seal More Info link
    $('.fundraising-seal a').click(function () {
        var seal = $(this).parents('.fundraising-seal');
        seal.toggleClass('expanded');
        seal.find('.more-info').slideToggle();
        return false;
    });

    // Setup State/Country field linkage
    $('.subfield-country').change(linkStateAndCountryField);

    // Show loading indicator after form button clicked and make validator play nicely with double submission logic
    //$('.form-buttons input').click(function () {
        // Remove the placeholder values before validating to avoid thinking the placeholder fulfills a field's requirements
        //$(this).parents('form.donation-form').each(stripPlaceholderValues);
/*
        if ($(this).parents('form.donation-form').data('validator').checkValidity() == true) {
            if ($(this).hasClass('submitted') == true) {
                return false;
            }
            $(this).next('.button-loading-indicator').show();
            $(this).addClass('submitted');
        } else {
            placeholder();
        }
*/
    //});

    // If there was a donation form error on the page, select the tab with an error
    $('.donation-form-error').each(function () {
        var tab_index = $(this).parents('.panel').prevAll().length; 
        var tabs = $(this).parents('.donation-form-wrapper').find('.tabs');
        if (tabs.length > 1) {
            tabs.data('tabs').click(tab_index); 
        }
    });

    // Handle tab=X on pluggable login form
    $('.login-portlet-wrapper').each(function () {
        var tab_index = _GET_VARS['tab'];
        if (tab_index != null) {
            $(this).find('.formTabs').data('tabs').click(parseInt(tab_index));
        }    
    });

    // Inject email=X value from url into __ac_name on login form
    $('input#__ac_name').each(function () {
        var email = _GET_VARS['email'];
        if (email != null) {
            $(this).val(email);
        }
    });

    // Cleanup issue with login portlet's handling of came_from
    $('.portletLogin input[name="came_from"]').each(function () {
        if ($(this).val() != _GET_VARS['came_from']) {
            $(this).val(_GET_VARS['came_from']);
        }
    });

    // Enforce integer only in quantity and amount fields
    $('.donation-form .field-amount input, .donation-form input.field-product-quantity').keydown(function(event) {
        // Allow: backspace, delete, tab, escape, and enter
        if ( event.keyCode == 46 || event.keyCode == 8 || event.keyCode == 9 || event.keyCode == 27 || event.keyCode == 13 || 
             // Allow: Ctrl+A
            (event.keyCode == 65 && event.ctrlKey === true) || 
             // Allow: home, end, left, right
            (event.keyCode >= 35 && event.keyCode <= 39)) {
                 // let it happen, don't do anything
                 return;
        }
        else {
            // Ensure that it is a number and stop the keypress
            if (event.shiftKey || (event.keyCode < 48 || event.keyCode > 57) && (event.keyCode < 96 || event.keyCode > 105 )) {
                event.preventDefault(); 
            }   
        }
    });
    
});})(jQuery);
