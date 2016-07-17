import json

from django.core import serializers
from django.db.models import Q, Count, Max
from django.shortcuts import render, redirect, get_object_or_404
from django.template import RequestContext
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, Http404
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist

from chunks.models import Chunk, Assignment, Milestone, SubmitMilestone, ReviewMilestone, Submission, StaffMarker
from review.old_routing import assign_tasks
from review.models import Comment, Vote, Task
from review.forms import CommentForm, ReplyForm, EditCommentForm
from accounts.forms import UserProfileForm
from accounts.models import UserProfile, Extension, Member
from log.models import Log

from pygments import highlight
from pygments.lexers import get_lexer_for_filename
from pygments.formatters import HtmlFormatter

import datetime
import sys
import logging


def longest_common_substring(s1, s2):
    m = [[0] * (1 + len(s2)) for i in xrange(1 + len(s1))]
    longest, x_longest = 0, 0
    for x in xrange(1, 1 + len(s1)):
        for y in xrange(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
    return s1[x_longest - longest: x_longest]

def markLogStart(user, log):
    logStart = Log(user=user, log='LOGSTART: '+str(log), timestamp=datetime.datetime.now())
    logStart.save()

def find_similar_comment(similar_comment_id, form_text):
    similar_comment = Comment.objects.get(id=similar_comment_id)
    overlap_length = len(longest_common_substring(form_text, similar_comment.text))
    if overlap_length > 20:
        return similar_comment
    else:
        return None

@login_required
def new_comment(request):
    if request.method == 'GET':
        start = int(request.GET['start'])
        end = int(request.GET['end'])
        chunk_id = request.GET['chunk']
        form = CommentForm(initial={
            'start': start,
            'end': end,
            'chunk': chunk_id
        })
        chunk = Chunk.objects.get(pk=chunk_id)
        markLogStart(request.user, {
            'type': 'new comment',
            'start': start,
            'end': end,
            'chunk': chunk_id
        })

        return render(request, 'review/comment_form.html', {
            'form': form,
            'start': start,
            'end': end,
            'snippet': chunk.generate_snippet(start, end),
            'chunk': chunk,
        })
    else:
        form = CommentForm(request.POST)
        if form.is_valid():
            try:
                form.similar_comment = find_similar_comment(form.cleaned_data['similar_comment'], form.cleaned_data['text'])
            except:
                form.similar_comment = None
            comment = form.save(commit=False)
            comment.author = request.user
            comment.save()
            user = request.user
            chunk = comment.chunk
            try:
                task = Task.objects.get(
                    chunk=chunk, reviewer=user)
                if task.status == 'N' or task.status == 'O':
                    task.mark_as('S')
            except Task.DoesNotExist:
                pass
            return render(request, 'review/comment.html', {
                'comment': comment,
                'chunk': chunk,
                'snippet': chunk.generate_snippet(comment.start, comment.end),
                'full_view': True,
                'file': chunk.file,
            })


@login_required
def reply(request):
    if request.method == 'GET':
        form = ReplyForm(initial={
            'parent': request.GET['parent']
        })
        markLogStart(request.user,  {
            'type': 'new reply',
            'parent': request.GET['parent'],
        })
        return render(request, 'review/reply_form.html', {'form': form})
    else:
        form = ReplyForm(request.POST)
        if form.is_valid():
            try:
                form.similar_comment = find_similar_comment(form.cleaned_data['similar_comment'], form.cleaned_data['text'])
            except:
                form.similar_comment = None
            comment = form.save(commit=False)
            comment.author = request.user
            parent = Comment.objects.get(id=comment.parent_id)
            chunk = parent.chunk
            comment.chunk = chunk
            comment.end = parent.end
            comment.start = parent.start
            if parent.is_reply():
                # strictly single threads for discussion
                comment.parent = parent.parent
            comment.save()
            try:
                task = Task.objects.get(chunk=comment.chunk,
                        reviewer=request.user)
                if task.status == 'N' or task.status == 'O':
                    task.mark_as('S')
            except Task.DoesNotExist:
                pass
            return render(request, 'review/comment.html', {
                'comment': comment,
                'chunk': chunk,
                'snippet': chunk.generate_snippet(comment.start, comment.end),
                'full_view': True,
                'file': chunk.file,
            })
@login_required
def edit_comment(request):
    if request.method == 'GET':
        comment_id = request.GET['comment_id']
        comment = Comment.objects.get(pk=comment_id)
        start = comment.start
        end = comment.end
        try:
            similar_comment = comment.similar_comment.id
        except:
            similar_comment = -1
        form = EditCommentForm(initial={
             'text': comment.text,
             'comment_id': comment.id,
             'similar_comment': similar_comment,
        })
        chunk = Chunk.objects.get(pk=comment.chunk.id)
        markLogStart(request.user,  {
            'type': 'edit comment',
            'text': comment.text,
            'comment_id': comment.id,
            'similar_comment': similar_comment,
        })
        return render(request, 'review/edit_comment_form.html', {
            'form': form,
            'start': start,
            'end': end,
            'snippet': chunk.generate_snippet(start, end),
            'chunk': chunk,
            'comment_id': comment.id,
            'reply': comment.is_reply(),
        })
    else:
        form = EditCommentForm(request.POST)
        if form.is_valid():
            comment_id = form.cleaned_data['comment_id']
            comment = Comment.objects.get(id=comment_id)
            comment.text = form.cleaned_data['text']
            comment.edited = datetime.datetime.now()
            try:
                comment.similar_comment = find_similar_comment(form.cleaned_data['similar_comment'], form.cleaned_data['text'])
            except:
                comment.similar_comment = None
            comment.save()
            chunk = comment.chunk
            return render(request, 'review/comment.html', {
                'comment': comment,
                'chunk': chunk,
                'snippet': chunk.generate_snippet(comment.start, comment.end),
                'full_view': True,
                'file': chunk.file,
            })

@login_required
def delete_comment(request):
    comment_id = request.GET['comment_id']
    comment = Comment.objects.get(pk=comment_id)
    if comment.author == request.user:
        # This will cascade and delete all replies as well
        comment.deleted = True
        comment.save()
    chunk = comment.chunk
    return render(request, 'review/comment.html', {
        'comment': comment,
        'chunk': chunk,
        'snippet': chunk.generate_snippet(comment.start, comment.end),
        'full_view': True,
        'file': chunk.file,
    })

@login_required
def vote(request):
    comment_id = request.POST['comment_id']
    value = request.POST['value']
    comment = Comment.objects.get(pk=comment_id)
    try:
        vote = Vote.objects.get(comment=comment, author=request.user)
        vote.value = value
    except Vote.DoesNotExist:
        vote = Vote(comment=comment, value=value, author=request.user)
    vote.save()
    # Reload the comment to make sure vote counts are up to date
    comment = Comment.objects.get(pk=comment_id)
    try:
        task = Task.objects.get(chunk=comment.chunk,
                reviewer=request.user)
        if task.status == 'N' or task.status == 'O':
            task.mark_as('S')
    except Task.DoesNotExist:
        pass
    response_json = json.dumps({
        'comment_id': comment_id,
        'upvote_count': comment.upvote_count,
        'downvote_count': comment.downvote_count,
    })
    return HttpResponse(response_json, mimetype='application/javascript')

@login_required
def unvote(request):
    comment_id = request.POST['comment_id']
    Vote.objects.filter(comment=comment_id, author=request.user).delete()
    # need to make sure to load the comment after deleting the vote to make sure
    # the vote counts are correct
    comment = Comment.objects.get(pk=comment_id)
    response_json = json.dumps({
        'comment_id': comment_id,
        'upvote_count': comment.upvote_count,
        'downvote_count': comment.downvote_count,
    })
    return HttpResponse(response_json, mimetype='application/javascript')

@login_required
def all_activity(request, review_milestone_id, username):
    user = request.user
    try:
        participant = User.objects.get(username__exact=username)
        #get all assignments
        review_milestone = ReviewMilestone.objects.select_related('submit_milestone', 'assignment__semester').get(id__exact=review_milestone_id)
        user_membership = Member.objects.get(user=user, semester=review_milestone.assignment.semester)
        if not user_membership.is_teacher() and not user==participant and not user.is_staff:
            raise Http404
    except Member.DoesNotExist:
        if not user.is_staff:
            raise Http404
    
    #get all relevant chunks
    chunks = Chunk.objects \
        .filter(file__submission__milestone= review_milestone.submit_milestone) \
        .filter(Q(comments__author=participant) | Q(comments__votes__author=participant)) \
        .select_related('comments__votes', 'comments__author_profile')
    chunk_set = set()
    review_milestone_data = []

    # lexer = JavaLexer()
    formatter = HtmlFormatter(cssclass='syntax', nowrap=True)
    for chunk in chunks:
        if chunk in chunk_set:
            continue
        else:
            chunk_set.add(chunk)
        lexer = get_lexer_for_filename(chunk.file.path)
        participant_votes = dict((vote.comment.id, vote.value) \
                for vote in participant.votes.filter(comment__chunk=chunk.id))
        numbers, lines = zip(*chunk.lines)

        staff_lines = StaffMarker.objects.filter(chunk=chunk).order_by('start_line', 'end_line')

        highlighted = zip(numbers,
                highlight(chunk.data, lexer, formatter).splitlines())

        highlighted_lines = []
        staff_line_index = 0
        for number, line in highlighted:
            if staff_line_index < len(staff_lines) and number >= staff_lines[staff_line_index].start_line and number <= staff_lines[staff_line_index].end_line:
                while staff_line_index < len(staff_lines) and number == staff_lines[staff_line_index].end_line:
                    staff_line_index += 1
                highlighted_lines.append((number, line, True))
            else:
                highlighted_lines.append((number, line, False))

        comments = chunk.comments.prefetch_related('votes', 'author__profile', 'author__membership__semester')
        highlighted_comments = []
        highlighted_votes = []
        for comment in comments:
            if comment.id in participant_votes:
                highlighted_votes.append(participant_votes[comment.id])
            else:
                highlighted_votes.append(None)
            if comment.author == participant:
                highlighted_comments.append(comment)
            else:
                highlighted_comments.append(None)
        comment_data = zip(comments, highlighted_comments, highlighted_votes)
        review_milestone_data.append((chunk, highlighted_lines, comment_data, chunk.file))

    return render(request, 'review/all_activity.html', {
        'review_milestone_data': review_milestone_data,
        'participant': participant,
        'activity_view': True,
        'full_view': True,
    })

def view_helper(comments):
    review_data = []
    for comment in comments:
        if comment.is_reply():
            #false means not a vote activity
            review_data.append(("reply-comment", comment, comment.generate_snippet(), False, None))
        else:
            review_data.append(("new-comment", comment, comment.generate_snippet(), False, None))
    review_data = sorted(review_data, key=lambda element: element[1].modified, reverse = True)
    return review_data

@login_required
def search(request):
    if request.method == 'POST':
        querystring = request.POST['value'].strip()
        if querystring:
            comments = Comment.objects.filter(chunk__file__submission__milestone__assignment__semester__is_current_semester=True,
                                              text__icontains = querystring)
            review_data = view_helper(comments[:15])
            return render(request, 'review/search.html', {
                                   'review_data': review_data,
                                   'query': querystring,
                                   'num_results': len(comments),
            })
    return render(request, 'review/search.html', {
                               'review_data': [],
                           })


@staff_member_required
def review_milestone_info(request, review_milestone_id):
    review_milestone = get_object_or_404(ReviewMilestone.objects.select_related('assignment__semester'), pk=review_milestone_id)
    submit_milestone = review_milestone.submit_milestone
    comments = Comment.objects.filter(chunk__file__submission__milestone__review_milestone=review_milestone)
    semester = review_milestone.assignment.semester

    total_chunks = Chunk.objects.filter(file__submission__milestone__review_milestone=review_milestone).count()
    alums_participating = Member.objects.filter(role=Member.VOLUNTEER, user__comments__chunk__file__submission__milestone__review_milestone=review_milestone).distinct().count()
    total_tasks = Task.objects.filter(milestone=review_milestone).count()
    assigned_chunks = Chunk.objects.filter(tasks__gt=0).filter(file__submission__milestone__review_milestone=review_milestone).distinct().count()
    total_chunks_with_human = Chunk.objects.filter(comments__type='U').filter(file__submission__milestone__review_milestone=review_milestone).distinct().count()
    total_comments = comments.count()
    total_checkstyle = comments.filter(type='S').count()
    total_staff_comments = comments.filter(author__membership__role=Member.TEACHER, author__membership__semester=semester).count()
    total_student_comments = comments.filter(author__membership__role=Member.STUDENT, author__membership__semester=semester).count()
    total_alum_comments = comments.filter(author__membership__role=Member.VOLUNTEER, author__membership__semester=semester).count()
    total_user_comments = comments.filter(type='U').count()
    zero_chunk_users = len(filter(lambda sub: len(sub.chunks()) == 0, submit_milestone.submissions.all()))

    return render(request, 'review/review_milestone_info.html', {
        'review_milestone': review_milestone,
        'total_chunks': total_chunks,
        'alums_participating': alums_participating,
        'total_tasks': total_tasks,
        'assigned_chunks': assigned_chunks,
        'total_chunks_with_human': total_chunks_with_human,
        'total_comments': total_comments,
        'total_checkstyle': total_checkstyle,
        'total_staff_comments': total_staff_comments,
        'total_student_comments': total_student_comments,
        'total_user_comments': total_user_comments,
        'total_alum_comments': total_alum_comments,
        'zero_chunk_users': zero_chunk_users,
    })

@staff_member_required
def stats(request):
    chunks = Chunk.objects.all()
    chunks_with_comments = \
            Chunk.objects.filter(comments__type='U') \
            .annotate(user_comment_count=Count('comments'))
    tasks = Task.objects.all()
    completed_tasks = Task.objects.filter(status='C')
    recent_comments = Comment.objects.filter(type='U').order_by('-created')[:10]
    return render(request, 'review/stats.html', {
        'chunks': chunks,
        'chunks_with_comments': chunks_with_comments,
        'tasks': tasks,
        'completed_tasks': completed_tasks,
        'recent_comments': recent_comments,
    })

@login_required
def change_task(request):
    task_id = request.REQUEST['task_id']
    status = request.REQUEST['status']
    task = get_object_or_404(Task, pk=task_id)
    task.mark_as(status)
    try:
        next_task = request.user.tasks.exclude(status='C').exclude(status='U') \
                                              .order_by('created')[0:1].get()
        return redirect('chunks.views.view_chunk', next_task.chunk_id) if next_task.chunk else redirect('chunks.views.view_all_chunks', 'all', next_task.submission_id)
    except Task.DoesNotExist:
        return redirect('dashboard.views.dashboard')

# => tasks
@login_required
def more_work(request):
    if request.method == 'POST':
        user = request.user
        new_task_count = 0
        current_tasks = user.tasks.exclude(status='C').exclude(status='U')
        total = 0
        if not current_tasks.count():
            live_review_milestones = ReviewMilestone.objects.filter(assigned_date__lt=datetime.datetime.now(),\
                duedate__gt=datetime.datetime.now(), assignment__semester__members_user=user).all()

            for milestone in live_review_milestones:
                current_tasks = user.tasks.filter(milestone=milestone)
                active_sub = Submission.objects.filter(name=user.username, milestone=milestone.reviewmilestone.submit_milestone)
                #do not give tasks to students who got extensions or already have tasks for this assignment
                if (not current_tasks.count()) and active_sub.count():
                    open_assignments = True
                    total += assign_tasks(milestone, user, tasks_to_assign=2)

            active_tasks = user.tasks \
                .select_related('chunk__file__submission__milestone__assignment') \
                .exclude(status='C') \
                .exclude(status='U') \
                .annotate(comment_count=Count('chunk__comments', distinct=True),
                          reviewer_count=Count('chunk__tasks', distinct=True))
            one = active_tasks.all()[0]
            two = active_tasks.all()[1]
            response_json = json.dumps({
                'total': total,
                'one': {"task_chunk_name": one.chunk.name, \
                                 "task_comment_count": one.comment_count,\
                                 "task_reviewer_count": one.reviewer_count, \
                                 "task_chunk_generate_snippet": one.chunk.generate_snippet(),\
                                 "task_id": one.id,\
                                 "task_chunk_id": one.chunk.id},
                'two': {"task_chunk_name": two.chunk.name, \
                                 "task_comment_count": two.comment_count,\
                                 "task_reviewer_count": two.reviewer_count, \
                                 "task_chunk_generate_snippet": two.chunk.generate_snippet(),\
                                 "task_id": two.id,\
                                 "task_chunk_id": two.chunk.id},
            })
            return HttpResponse(response_json, mimetype='application/javascript')
    return render(request, 'accounts/manage.html', {
    })

@staff_member_required
def cancel_assignment(request):
    if request.method == 'POST':
        assignments = request.POST.get('assignment', None)
        if assignments == "all":
            started_tasks = Task.objects.filter(status='S')
            started = 0
            for task in started_tasks:
                task.mark_as('C')
                started += 1
            unfinished_tasks = Task.objects.exclude(status='C').exclude(status='U')
            total = 0
            for task in unfinished_tasks:
                total += 1
                task.mark_as('U')
            response_json = json.dumps({
                'total': total,
            })
            return HttpResponse(response_json, mimetype='application/javascript')
    return render(request, 'accounts/manage.html', {
    })


