import os
import datetime
from chunks.models import Chunk, Assignment, Semester

from sorl.thumbnail import ImageField

from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.conf import settings
from django.dispatch import receiver

class Token(models.Model):
    expire = models.DateTimeField(null=True, blank=True)
    code = models.CharField(null=True, blank=True, max_length=20)

class Extension(models.Model):
    user = models.ForeignKey(User, related_name='extensions')
    assignment = models.ForeignKey(Assignment, related_name='extensions')
    slack_used = models.IntegerField(default=0, blank=True, null=True)

class Member(models.Model):
    role = models.CharField(max_length=16)
    slack_budget = models.IntegerField(default=5, blank=False, null=False)
    user = models.ForeignKey(User, related_name='membership')
    semester = models.ForeignKey(Semester, related_name='members')

class UserProfile(models.Model):
    # def get_photo_path(instance, filename):
    #     return os.path.join(
    #             settings.PROFILE_PHOTO_DIR,
    #             instance.user.username,
    #             filename)

    ROLE_CHOICES = (
        ('T', 'Teaching staff'),
        ('S', 'Student'),
    )
    SEMESTER_CHOICES = (
        ('FA11', "Fall 2011"),
        ('SP12', "Spring 2012"),
        ('FA12', "Fall 2012"),
        ('SP13', "Spring 2013"),
    )
    user = models.OneToOneField(User, related_name='profile')
    # photo = ImageField(upload_to=get_photo_path)
    assigned_chunks = models.ManyToManyField(Chunk, through='tasks.Task',
        related_name='reviewers')
    reputation = models.IntegerField(default=0, editable=True)
    role = models.CharField(max_length=1, choices=ROLE_CHOICES,
                            blank=True, null=True)
    semester_taken = models.CharField(max_length=4, choices=SEMESTER_CHOICES,
                                      blank=True, null=True)

    token = models.ForeignKey(Token, related_name='invited', default=None, null=True)
    def __unicode__(self):
        return self.user.__unicode__()

    def is_staff(self):
        return self.role == 'T'

    def is_student(self):
        return self.role == 'S'

    def is_alum(self):
        return not is_staff() and not is_student() and not is_checkstyle()

    def role_str(self):
      if self.is_student():
        return 'Student'
      elif self.is_staff():
        return 'Staff'
      return 'Other'

    def is_checkstyle(self):
      return self.user.username == 'checkstyle'

    def name(self):
      if self.user.first_name and self.user.last_name:
        return self.user.first_name + ' ' + self.user.last_name
      return self.user.username

    def extension_days(self):
      total_days = 5 #TODO: change after multi-class refactor
      used_days = sum([extension.slack_used for extension in self.extensions.all()])
      return total_days - used_days

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        profile, created = UserProfile.objects.get_or_create(user=instance)
        if created:
            profile.role = 'S'
            profile.save()

