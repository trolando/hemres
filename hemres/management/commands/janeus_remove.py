from __future__ import print_function
from django.conf import settings
from django.core.management.base import BaseCommand
from hemres import models
from janeus import Janeus


class Command(BaseCommand):
    help = 'Remove a Janeus user'

    def handle(self, *args, **kwargs):
        if not hasattr(settings, 'JANEUS_SERVER'):
            print("Janeus is not configured!")
            return

        if len(args) != 1:
            print("Please provide one arguments")
            return

        # get member_id and label from args
        member_id = int(args[0])
        label = str(args[1])

        # retrieve Janeus subscriber
        for s in models.JaneusSubscriber.objects.filter(member_id=int(member_id)):
            s.delete()