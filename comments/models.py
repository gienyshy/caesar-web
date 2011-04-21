from caesar.chunks.models import Chunk
from django.contrib.auth.models import User

from django.db import models

class Comment(models.Model):
    text = models.TextField()
    chunk = models.ForeignKey(Chunk, related_name='comments')
    author = models.ForeignKey(User)
    start = models.IntegerField() # region start line, inclusive
    end = models.IntegerField() # region end line, exclusive
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    parent = models.ForeignKey('self', related_name='child_comments', 
        blank=True, null=True)
    class Meta:
        ordering = [ 'start', 'end' ]
