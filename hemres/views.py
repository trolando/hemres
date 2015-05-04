from __future__ import unicode_literals
from future.builtins import int
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.generic.edit import UpdateView
import hashlib
import os
import html2text

from janeus import Janeus

from . import models
from . import forms


def view_home(request):
    if getattr(settings, 'RECAPTCHA', False):
        if request.method == 'POST':
            form = forms.SubscriptionEmailRecaptchaForm(request.POST)
        else:
            form = forms.SubscriptionEmailRecaptchaForm()
    else:
        if request.method == 'POST':
            form = forms.SubscriptionEmailForm(request.POST)
        else:
            form = forms.SubscriptionEmailForm()

    if request.method == 'POST':
        if form.is_valid():
            email = form.cleaned_data['email']
            if getattr(settings, 'HEMRES_DONT_EMAIL', False):
                email_to_send, attachments = compose_mail(email, False, request=request)
                return HttpResponse(email_to_send, content_type='text/html')
            else:
                send_mail(email, request=request)
                return render(request, 'hemres/subscriptions_emailsent.html', {'email': email})

    return render(request, 'hemres/home.html', {'form': form})


def subscriptions_done(request):
    return render(request, 'hemres/subscriptions_manage_done.html')


class ManageEmailSubscriptions(UpdateView):
    model = models.EmailSubscriber
    form_class = forms.EmailSubscriberForm
    template_name = 'hemres/subscriptions_manage_email.html'

    def get_success_url(self):
        return reverse(subscriptions_done)

    def get_object(self, *args, **kwargs):
        subscriber = self.kwargs['subscriber']
        token = self.kwargs['token']
        accesstoken = models.EmailSubscriberAccessToken.objects.filter(pk=int(subscriber)).filter(token=token).filter(expiration_date__gt=timezone.now())
        # check expire
        if len(accesstoken) == 0:
            raise Http404()
        return accesstoken[0].subscriber


class ManageJaneusSubscriptions(UpdateView):
    model = models.JaneusSubscriber
    form_class = forms.JaneusSubscriberForm
    template_name = 'hemres/subscriptions_manage_janeus.html'

    def get_success_url(self):
        return reverse(subscriptions_done)

    def get_object(self, *args, **kwargs):
        subscriber = self.kwargs['subscriber']
        token = self.kwargs['token']
        accesstoken = models.JaneusSubscriberAccessToken.objects.filter(pk=int(subscriber)).filter(token=token).filter(expiration_date__gt=timezone.now())
        # check expire
        if len(accesstoken) == 0:
            raise Http404()
        accesstoken[0].subscriber.update_janeus_newsletters()
        return accesstoken[0].subscriber


def make_janeus_subscriber(members):
    member_id, name = members
    s = models.JaneusSubscriber.objects.filter(member_id=int(member_id)).select_related('token')
    if len(s) == 0:
        s = [models.JaneusSubscriber(member_id=int(member_id), janeus_name=name, name=name)]
        s[0].save()
    return s[0]


def create_fresh_janeus_token(subscriber):
    if hasattr(subscriber, 'token'):
        subscriber.token.delete()
    token = hashlib.sha256(os.urandom(64)).hexdigest()
    t = models.JaneusSubscriberAccessToken(subscriber=subscriber, token=token)
    t.save()
    return t


def create_fresh_email_token(subscriber):
    if hasattr(subscriber, 'token'):
        subscriber.token.delete()
    token = hashlib.sha256(os.urandom(64)).hexdigest()
    t = models.EmailSubscriberAccessToken(subscriber=subscriber, token=token)
    t.save()
    return t


def send_mail(emailaddress, request):
    # knowledge of 'request' necessary to compose mail
    email_to_send, attachments = compose_mail(emailaddress, True, request=request)
    subject = 'Jonge Democraten Nieuwsbrieven'
    from_email = getattr(settings, 'HEMRES_FROM_ADDRESS', 'noreply@jongedemocraten.nl')
    msg = EmailMultiAlternatives(subject=subject, body=email_to_send, from_email=from_email, to=[emailaddress])
    # msg.attach_alternative(email_to_send, "text/html")
    msg.content_subtype = "html"
    msg.mixed_subtype = 'related'
    for a in attachments:
        msg.attach(a)
    msg.send()


@transaction.atomic
def compose_mail(emailaddress, embed, request):
    # find Janeus users
    if hasattr(settings, 'JANEUS_SERVER'):
        janeus_subscribers = [make_janeus_subscriber(s) for s in Janeus().lidnummers(emailaddress)]
    else:
        janeus_subscribers = []

    email_subscribers = models.EmailSubscriber.objects.filter(email=emailaddress).select_related('token')  # case sensitive!

    if len(janeus_subscribers) == 0 and len(email_subscribers) == 0:
        email_subscribers = [models.EmailSubscriber(name='', email=emailaddress)]
        email_subscribers[0].save()

    # create tokens
    janeus_subscribers_tokens = [create_fresh_janeus_token(s) for s in janeus_subscribers]
    email_subscribers_tokens = [create_fresh_email_token(s) for s in email_subscribers]

    if len(janeus_subscribers) == 1 and len(email_subscribers) == 0:
        name = janeus_subscribers[0].name
    else:
        name = None

    absolute_uri = '%s://%s' % (request.scheme, request.get_host())

    context = {'janeus_subscriber_tokens': janeus_subscribers_tokens,
               'email_subscriber_tokens': email_subscribers_tokens,
               'attachments': {},
               'render_mail': embed,
               'absolute_uri': absolute_uri,
               'name': name}
    result = render_to_string('hemres/subscriptions_email.html', context)
    return result, [mime for mime, cid in list(context['attachments'].values())]


@staff_member_required
def create_newsletter(request):
    if request.method == 'POST':
        form = forms.CreateNewsletterForm(request.POST)
    else:
        form = forms.CreateNewsletterForm()

    if request.method == 'POST':
        if form.is_valid():
            template = form.cleaned_data['template']
            newsletter = template.create_newsletter('Untitled')
            content_type = ContentType.objects.get_for_model(newsletter.__class__)
            return redirect(reverse('admin:%s_%s_change' % (content_type.app_label, content_type.model), args=(newsletter.id,)))

    return render(request, 'hemres/create_newsletter.html', {'form': form})


def view_newsletter(request, newsletter_pk):
    if request.user.is_active and request.user.is_staff:
        newsletter = get_object_or_404(models.Newsletter, pk=newsletter_pk)
    else:
        newsletter = get_object_or_404(models.Newsletter.objects.filter(public=True), pk=newsletter_pk)
    subscriptions_url = request.build_absolute_uri(reverse(view_home))
    email, attachments = newsletter.render('', False, subscriptions_url)
    return HttpResponse(email, content_type="text/html")


@staff_member_required
def test_newsletter(request, pk):
    newsletter = get_object_or_404(models.Newsletter, pk=pk)
    if request.method == 'POST':
        form = forms.TestEmailForm(request.POST)
    else:
        form = forms.TestEmailForm()

    if request.method == 'POST':
        if form.is_valid():
            address = form.cleaned_data['email']
            subscriptions_url = request.build_absolute_uri(reverse(view_home))
            subject = "[Test] {}".format(newsletter.subject)
            html_content, attachments = newsletter.render('', True, subscriptions_url)

            h = html2text.HTML2Text()
            h.ignore_images = True
            text_content = h.handle(html_content)
            from_email = getattr(settings, 'HEMRES_FROM_ADDRESS', 'noreply@jongedemocraten.nl')

            msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, to=[address])
            msg.attach_alternative(html_content, "text/html")
            msg.mixed_subtype = 'related'
            for a in attachments:
                msg.attach(a)

            if getattr(settings, 'HEMRES_DONT_EMAIL', False):
                return HttpResponse(msg.message().as_string(), content_type="message")
            else:
                msg.send()
                content_type = ContentType.objects.get_for_model(newsletter.__class__)
                return redirect(reverse('admin:%s_%s_changelist' % (content_type.app_label, content_type.model)))

    return render(request, 'hemres/test_newsletter.html', {'form': form, 'nieuwsbrief': str(newsletter)})


@staff_member_required
def prepare_sending(request, pk):
    newsletter = get_object_or_404(models.Newsletter, pk=pk)
    if request.method == 'POST':
        form = forms.PrepareSendingForm(request.POST)
    else:
        form = forms.PrepareSendingForm()

    if request.method == 'POST':
        if form.is_valid():
            subscriptions_url = request.build_absolute_uri(reverse(view_home))
            newsletter.prepare_sending(form.cleaned_data['lists'], subscriptions_url)
            content_type = ContentType.objects.get_for_model(newsletter.__class__)
            return redirect(reverse('admin:%s_%s_changelist' % (content_type.app_label, content_type.model)))

    return render(request, 'hemres/prepare_sending.html', {'form': form, 'nieuwsbrief': str(newsletter)})


@staff_member_required
def process_sending(request, pk):
    newsletter_to_list = get_object_or_404(models.NewsletterToList, pk=pk)
    newsletter_to_list.process()
    send_tasks()
    content_type = ContentType.objects.get_for_model(models.NewsletterToList)
    return redirect(reverse('admin:%s_%s_changelist' % (content_type.app_label, content_type.model)))


def send_mail(pk):
    try:
        ns = models.NewsletterToSubscriber.objects.get(pk=pk)
        ns.send_mail()
    except:
        pass


def send_tasks():
    # This fails (silently) if django_rq is not available.
    try:
        import django_rq
        for ns in models.NewsletterToSubscriber.objects.all():
            django_rq.enqueue(send_mail, ns.pk, timeout=10)
    except:
        pass
