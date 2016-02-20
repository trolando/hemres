from __future__ import unicode_literals
from future.builtins import super
from future.builtins import str
from future.builtins import int
from builtins import object
from django.contrib.sites.models import Site
from django.forms import Form, EmailField, ModelForm, ModelMultipleChoiceField, ModelChoiceField, CharField
from django.forms.widgets import CheckboxSelectMultiple, CheckboxFieldRenderer, CheckboxChoiceInput, RadioSelect
from django.utils.safestring import mark_safe
from fullcalendar.models import Occurrence
import re

from . import models


class SubscriptionEmailForm(Form):
    email = EmailField(max_length=254, label='Emailadres:')


class SubscriptionEmailRecaptchaForm(SubscriptionEmailForm):
    def __init__(self, *args, **kwargs):
        super(SubscriptionEmailRecaptchaForm, self).__init__(*args, **kwargs)
        from captcha.fields import ReCaptchaField
        self.captcha = ReCaptchaField()


class CheckboxChoiceInputDisabled(CheckboxChoiceInput):
    def __init__(self, *args, **kwargs):
        disabledset = kwargs.pop('disabledset', None)
        super(CheckboxChoiceInputDisabled, self).__init__(*args, **kwargs)
        self.disabledset = set([str(x.pk) for x in disabledset])
        if self.choice_value in self.disabledset:
            self.attrs['disabled'] = 'disabled'


class CheckboxFieldDisabledRenderer(CheckboxFieldRenderer):
    def choice_input_class(self, *args, **kwargs):
        kwargs = dict(kwargs, disabledset=self.disabledset)
        return CheckboxChoiceInputDisabled(*args, **kwargs)


class CheckboxSelectMultipleDisabled(CheckboxSelectMultiple):
    def renderer(self, *args, **kwargs):
        instance = CheckboxFieldDisabledRenderer(*args, **kwargs)
        instance.disabledset = self.disabledset
        return instance


class CheckboxSelectMultipleRenderer(CheckboxFieldRenderer):
    def render(self):
        result = super(CheckboxSelectMultipleRenderer, self).render()
        return mark_safe(re.sub("<ul id", '<ul class="checkboxlist" id', result, count=1))


class CheckboxSelectMultipleCss(CheckboxSelectMultiple):
    renderer = CheckboxSelectMultipleRenderer


class ModelMultipleChoiceFieldDisabled(ModelMultipleChoiceField):
    widget = CheckboxSelectMultipleDisabled

    def __init__(self, disabledset=[], *args, **kwargs):
        super(ModelMultipleChoiceFieldDisabled, self).__init__(*args, **kwargs)
        self.widget.disabledset = disabledset


class EventField(ModelMultipleChoiceField):
    def __init__(self, *args, **kwargs):
        super(EventField, self).__init__(*args, **kwargs)
        # get all sites in occurrences
        sites = list(Site.objects.filter(occurrence__in=tuple(self.queryset)).order_by('name'))
        # fill choices
        self.choices = []
        for site in sites:
            # get occurrences for this site
            occurrences = self.queryset.filter(site=site)
            # convert to (value, label)
            occurrences = (tuple((self.prepare_value(o), self.label_from_instance(o))) for o in occurrences)
            # add to choices
            self.choices.append(tuple((site.name, tuple(occurrences))))


class JaneusSubscriberForm(ModelForm):
    subscriptions = ModelMultipleChoiceFieldDisabled(
        queryset=models.MailingList.objects.order_by('name'),
        required=False,
        label='Nieuwsbrieven')

    class Meta(object):
        model = models.JaneusSubscriber
        fields = ('name', 'subscriptions')

    def __init__(self, *args, **kwargs):
        super(JaneusSubscriberForm, self).__init__(*args, **kwargs)
        self.fields['name'].label = "Naam"
        allowed = self.instance.get_allowed_newsletters()
        self.fields['subscriptions'].queryset = models.MailingList.objects.filter(pk__in=[int(o.pk) for o in allowed]).order_by('name')

    def save(self, *args, **kwargs):
        result = super(JaneusSubscriberForm, self).save(*args, **kwargs)
        result.update_janeus_newsletters()
        return result


class EmailSubscriberForm(ModelForm):
    subscriptions = ModelMultipleChoiceField(
        queryset=models.MailingList.objects.filter(janeus_groups_required='').order_by('name'),
        required=False,
        widget=CheckboxSelectMultiple,
        label='Nieuwsbrieven')

    class Meta(object):
        model = models.EmailSubscriber
        fields = ('name', 'subscriptions')

    def __init__(self, *args, **kwargs):
        super(EmailSubscriberForm, self).__init__(*args, **kwargs)
        self.fields['name'].label = "Naam"

    def save(self, *args, **kwargs):
        result = super(EmailSubscriberForm, self).save(*args, **kwargs)
        result.remove_restricted_newsletters()
        return result


class CreateNewsletterForm(Form):
    subject = CharField(required=True, label='Onderwerp')

    template = ModelChoiceField(
        queryset=models.NewsletterTemplate.objects.filter().order_by('title'),
        required=True,
        widget=RadioSelect,
        empty_label=None,
        label='Template')

    events = EventField(
        queryset=Occurrence.objects.upcoming().order_by('start_time'),
        required=False,
        widget=CheckboxSelectMultipleCss,
        label='Events')


class TestEmailForm(Form):
    email = EmailField(max_length=254, label='Emailadres:')


class PrepareSendingForm(Form):
    lists = ModelChoiceField(
        queryset=models.MailingList.objects.filter().order_by('name'),
        required=True,
        widget=RadioSelect,
        empty_label=None,
        label='Nieuwsbrieven')
