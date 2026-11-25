"""Adapt legacy operating-chain requests to the existing project publisher."""


def publish_operating_chain(root, args, profile, tool):
    from .project_publication_tools import ProjectPublicationTools, PublishInitializeProject

    sources = {
        name: getattr(args, name).model_dump()
        for name in ('depot_template', 'trains_template', 'courses_template', 'timetable_template')
    }
    sources.update({name: getattr(args.infrastructure, name).model_dump() for name in ('header', 'shapes')})
    project = args.model_dump(exclude={
        'domain': True,
        'depot_template': True,
        'trains_template': True,
        'courses_template': True,
        'timetable_template': True,
        'preview_only': True,
        'target_directory': True,
        'infrastructure': {'domain', 'header', 'shapes', 'preview_only', 'target_directory'},
    })
    request = PublishInitializeProject.model_validate({
        'sources': sources,
        'profile': profile,
        'project': project,
        'preview_only': False,
        'target_directory': args.target_directory,
    })
    result = ProjectPublicationTools(root).initialize(request)
    return {**result, 'tool': tool, 'report': result['candidate_receipt']['chain_receipt']}
