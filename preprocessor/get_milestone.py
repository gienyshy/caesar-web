from review.models import *

# args: command-line args returned by ArgumentParser.parse_args.
# Assumes has subject, semester, and milestone arguments,
#   as used by preprocess.py and takeSnapshots.py.
# returns SubmitMilestone object or throws error
def get_milestone(args):
    if args.milestone:
        return SubmitMilestone.objects.get(id=args.milestone)
    else:
        if not args.subject:
            raise Exception("need to specify either --subject or --milestone.  See --help for details.")

        if args.semester:
            semester = Semester.objects.get(\
                subject__name=args.subject[0],
                semester=args.semester[0])
        else:
            # find the most recent milestone for the subject, and use its semester
            milestones = SubmitMilestone.objects.filter(\
                assignment__semester__subject__name=args.subject[0])\
                .order_by('-duedate')
            if len(milestones) == 0:
                raise Exception(str(args.subject) + " has no submit milestones")
            semester = milestones[0].assignment.semester

        milestones = SubmitMilestone.objects.filter(\
            assignment__semester=semester,
            duedate__lte=datetime.datetime.now())\
            .order_by('-duedate')
        if len(milestones) == 0:
            raise Exception(str(semester) + " has no submit milestones that have passed")
        return milestones[0]
