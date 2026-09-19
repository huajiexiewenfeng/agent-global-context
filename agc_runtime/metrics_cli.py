"""Explicit workflow; only evaluate/evaluate-research/classify-research call models."""
from __future__ import annotations

import argparse
import json
from uuid import uuid4
from pathlib import Path

from agc_runtime.metrics_collect import collect_batch
from agc_runtime.metrics_compute import compute_metrics
from agc_runtime.metrics_models import canonical, validate_batch
from agc_runtime.metrics_report import render_report
from agc_runtime.metrics_eval import prepare_plan
from agc_runtime.metrics_review import append_revision


def _read_plan_input(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result

    limit = 32 * 1024 * 1024
    with path.open('rb') as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('plan_input_too_large')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='agc-metrics')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Read explicitly supplied metadata sources; no model call')
    for field in ('start', 'end', 'output'):
        prepare.add_argument('--'+field, required=True)
    prepare.add_argument('--cutoff')
    prepare.add_argument('--synthetic', action='store_true', help='Label supplied fixture data as synthetic; does not generate data')
    for field in ('trace-db','eval-db','receipts-dir','attempts-dir','business-dir'):
        prepare.add_argument('--'+field, type=Path)
    render = commands.add_parser('render', help='Render a frozen batch without live reads')
    render.add_argument('--batch', type=Path, required=True)
    render.add_argument('--review', type=Path, help='Optional frozen review annex from the same batch')
    render.add_argument('--research-cohort',type=Path,help='Optional frozen task selection coverage, not a quality denominator')
    render.add_argument('--research-preparation',type=Path,help='Optional content-free preparation manifest; no source reads')
    render.add_argument('--evidence',type=Path,help='Explicit existing evidence annex; renders references only, requires matching review')
    render.add_argument('--revisions-dir', type=Path, help='Optional append-only human feedback directory')
    render.add_argument('--output', type=Path, required=True)
    plan = commands.add_parser('plan', help='Freeze an evaluation plan for review; no model call')
    for field in ('batch', 'cases', 'judge', 'rules', 'output'):
        plan.add_argument('--'+field, type=Path, required=True)
    review_command = commands.add_parser('review', help='Append explicit human feedback; never modify Judge results')
    for field in ('batch', 'review', 'feedback', 'revisions-dir'):
        review_command.add_argument('--'+field, type=Path, required=True)
    capture_plan = commands.add_parser('prepare-capture-plan', help='Resolve selected Capture references and freeze a plan; no model call')
    for field in ('batch','references','output'):
        capture_plan.add_argument('--'+field,type=Path,required=True)
    evaluate = commands.add_parser('evaluate', help='Explicitly authorized Capture metrics evaluation with fixed host binding')
    for field in ('batch','plan','source-map','output'):
        evaluate.add_argument('--'+field,type=Path,required=True)
    evaluate.add_argument('--consent',required=True,help='Exact plan authorization digest approved by the user')
    cohort = commands.add_parser('research-cohort', help='Freeze explicit frontend task classifications; no discovery or model call')
    for field in ('batch','tasks','classifier','output'):
        cohort.add_argument('--'+field,type=Path,required=True)
    research_plan=commands.add_parser('prepare-research-plan',help='Resolve selected historical tasks into a plan; no model call')
    for field in ('batch','cohort','references','output'):
        research_plan.add_argument('--'+field,type=Path,required=True)
    research_eval=commands.add_parser('evaluate-research',help='Explicitly authorized historical research evaluation')
    for field in ('batch','cohort','references','plan','source-map','output'):
        research_eval.add_argument('--'+field,type=Path,required=True)
    research_eval.add_argument('--consent',required=True,help='Exact plan authorization digest approved by the user')
    research_inputs=commands.add_parser('research-inputs',help='Return private inputs for classifying explicitly scoped tasks; no model call')
    for field in ('batch','references'):
        research_inputs.add_argument('--'+field,type=Path,required=True)
    classification_plan=commands.add_parser('prepare-classification-plan',help='Prepare a content-free classification authorization plan; no model call')
    classification_run=commands.add_parser('classify-research',help='Explicitly authorized input-only research task classification')
    for command in (classification_plan,classification_run):
        for field in ('batch','references','output'):
            command.add_argument('--'+field,type=Path,required=True)
    classification_run.add_argument('--plan',type=Path,required=True)
    classification_run.add_argument('--consent',required=True,help='Exact classification authorization digest approved by the user')
    classification_export=commands.add_parser('export-classification',help='Verify saved classification against live sources and export cohort; no model call')
    for field in ('batch','references','plan','execution-dir','output'):
        classification_export.add_argument('--'+field,type=Path,required=True)
    evidence_export=commands.add_parser('export-review-evidence',help='Export verified evidence references without source/model text; no Judge call')
    for field in ('batch','review','source-map','execution-dir','output'):
        evidence_export.add_argument('--'+field,type=Path,required=True)
    evidence_export.add_argument('--cohort',type=Path,help='Required for research cases')
    evidence_export.add_argument('--references',type=Path,help='Selected native references; required for research cases')
    args = parser.parse_args(argv)
    model_called = False
    response_extra = {}
    try:
        if getattr(args, 'revisions_dir', None) is not None:
            # Preserve path components for the private-root reparse checks;
            # resolve() here would hide linked directories before validation.
            args.revisions_dir = args.revisions_dir.expanduser().absolute()
        if args.command == 'prepare':
            output = Path(args.output).expanduser().resolve()
            if output.exists():
                raise ValueError('output_exists')
            if args.receipts_dir and output.is_relative_to(args.receipts_dir.expanduser().resolve()):
                raise ValueError('output_inside_source')
            if args.attempts_dir and output.is_relative_to(args.attempts_dir.expanduser().resolve()):
                raise ValueError('output_inside_source')
            if args.business_dir and output.is_relative_to(args.business_dir.expanduser().resolve()):
                raise ValueError('output_inside_source')
            batch = collect_batch(start=args.start, end=args.end, cutoff=args.cutoff or args.end,
                trace_db=args.trace_db, eval_db=args.eval_db, receipts_dir=args.receipts_dir,
                data_kind='synthetic' if args.synthetic else 'observed', attempts_dir=args.attempts_dir, business_dir=args.business_dir)
            html = render_report(batch)
            metrics = compute_metrics(batch)
            output.mkdir(parents=True, exist_ok=False)
            for name, value in (('batch.json', canonical(batch)), ('metrics.json', canonical(metrics)), ('report.html', html)):
                with (output / name).open('x', encoding='utf-8', newline='\n') as handle:
                    handle.write(value)
        elif args.command in ('prepare-capture-plan','evaluate','prepare-research-plan','evaluate-research'):
            from agc_runtime.metrics_host import load_host, output_directory
            from agc_runtime.metrics_capture_plan import prepare_capture_plan, capture_plan_resolver
            from agc_runtime.metrics_eval import validate_plan, check_authorization
            from agc_runtime.metrics_execution import _write
            from agc_runtime.metrics_runner import run_plan
            from agc_runtime.metrics_review_batch import freeze_review
            from agc_runtime.metrics_research_cohort import validate_research_cohort
            from agc_runtime.metrics_research_plan import prepare_research_plan, research_plan_resolver
            batch=validate_batch(_read_plan_input(args.batch))
            context=load_host()
            executing=args.command in ('evaluate','evaluate-research')
            output=output_directory(args.output,context,existing=executing)
            if not executing:
                if args.command=='prepare-research-plan':
                    cohort=validate_research_cohort(batch,_read_plan_input(args.cohort))
                    source=context['research_source_factory'](_read_plan_input(args.references))
                    source.validate_cohort(cohort)
                    prepared=prepare_research_plan(batch,cohort,source=source,judge=context['gateway'].configuration)
                else:
                    prepared=prepare_capture_plan(batch,_read_plan_input(args.references),
                        source=context['source'],judge=context['gateway'].configuration)
                output.mkdir(exist_ok=False)
                _write(output/'plan.json',prepared['plan'])
                _write(output/'source-map.json',prepared['source_map'])
            else:
                planned=validate_plan(_read_plan_input(args.plan))
                if planned['batch_id']!=batch['batch_id']:
                    raise ValueError('evaluation_batch_mismatch')
                check_authorization(planned,args.consent,revoked_refs=[])
                from agc_runtime.metrics_source_bindings import evaluation_source_bindings,register_source_bindings
                source_map=_read_plan_input(args.source_map)
                if args.command=='evaluate-research':
                    cohort=validate_research_cohort(batch,_read_plan_input(args.cohort))
                    native_references=_read_plan_input(args.references)
                    source=context['research_source_factory'](native_references)
                    source.validate_cohort(cohort)
                    resolver=research_plan_resolver(batch,cohort,planned,source_map,source=source)
                    source_bindings=evaluation_source_bindings(planned,source_map,native_references=native_references)
                else:
                    resolver=capture_plan_resolver(planned,source_map,source=context['source'])
                    source_bindings=evaluation_source_bindings(planned,source_map)
                # If orchestration raises after a send, do not claim no model
                # was called merely because the final report was not written.
                model_called=None
                try:
                    register_source_bindings(context['ledger'],source_bindings)
                    result=run_plan(planned,directory=output,ledger_directory=context['ledger'],
                        consent_digest=args.consent,gateway=context['gateway'],resolve_case=resolver,
                        require_source_binding=True,commit_guard=context['commit_guard'])
                finally:
                    model_called=context['gateway'].call_attempts>0
                revision=uuid4().hex
                review_path=output/('review-'+revision+'.json')
                report_path=output/('report-'+revision+'.html')
                from agc_runtime.metrics_report_artifacts import publish_bundle
                def build_report():
                    # freeze_review can retain unavailable rows; publication must
                    # not recreate a source-derived report after source forget.
                    for case in planned['cases']: resolver(case['case_id'])
                    review=freeze_review(batch,planned,output,resolve_case=resolver,ledger_directory=context['ledger'],require_source_binding=True)
                    html=render_report(batch,review=review)
                    for case in planned['cases']: resolver(case['case_id'])
                    return {'run-'+revision+'.json':canonical(result),review_path.name:canonical(review),report_path.name:html}
                publish_bundle(context=context,plan_id=planned['plan_id'],directory=output,
                    kind='quality_report',revision=revision,build=build_report)
                response_extra=dict(review_file=str(review_path),report_file=str(report_path),
                                    model_call_attempts=context['gateway'].call_attempts,
                                    entries=result['entries'])
        elif args.command in ('prepare-classification-plan','classify-research'):
            from agc_runtime.metrics_host import load_host,output_directory
            from agc_runtime.metrics_research_inputs import prepare_research_inputs
            from agc_runtime.metrics_classification_execution import prepare_classification_plan,execute_classification
            from agc_runtime.metrics_execution import _write
            batch=validate_batch(_read_plan_input(args.batch))
            context=load_host()
            executing=args.command=='classify-research'
            output=output_directory(args.output,context,existing=executing)
            references=_read_plan_input(args.references)
            def resolve():
                return prepare_research_inputs(batch,references,source_factory=context['research_source_factory'])
            if not executing:
                preparation=resolve()
                planned=prepare_classification_plan(batch,preparation,judge=context['gateway'].configuration)
                output.mkdir(exist_ok=False)
                _write(output/'plan.json',planned)
                _write(output/'preparation-manifest.json',preparation['manifest'])
                response_extra=dict(plan_file=str(output/'plan.json'),authorization_digest=planned['authorization_digest'],
                                    input_count=planned['input_count'],max_calls=planned['max_calls'])
            else:
                planned=_read_plan_input(args.plan)
                model_called=None
                try:
                    result=execute_classification(batch,planned,directory=output,ledger_directory=context['ledger'],
                        consent_digest=args.consent,gateway=context['gateway'],resolve_preparation=resolve,
                        native_references=references,commit_guard=context['commit_guard'])
                finally:
                    model_called=context['gateway'].call_attempts>0
                response_extra=dict(classification_status=result['status'],
                                    model_call_attempts=context['gateway'].call_attempts,
                                    execution_directory=str(output/planned['plan_id']) if planned['max_calls'] else None)
        elif args.command=='export-classification':
            from agc_runtime.metrics_host import load_host,output_directory
            from agc_runtime.metrics_research_inputs import prepare_research_inputs
            from agc_runtime.metrics_classification_reader import read_classification
            from agc_runtime.metrics_execution import _write,_now
            from agc_runtime.metrics_models import digest
            batch=validate_batch(_read_plan_input(args.batch))
            context=load_host()
            output=output_directory(args.output,context,existing=False)
            execution=output_directory(args.execution_dir,context,existing=True)
            references=_read_plan_input(args.references)
            planned=_read_plan_input(args.plan)
            from agc_runtime.metrics_report_artifacts import publish_bundle
            checked_export={}
            def build_classification_export():
                checked=read_classification(batch,planned,directory=execution,ledger_directory=context['ledger'],require_source_binding=True,
                    resolve_preparation=lambda:prepare_research_inputs(batch,references,source_factory=context['research_source_factory']))
                checked_export.update(checked)
                classification=checked['classification']
                verification=dict(schema_version='agc.classification-export.v1',plan_id=planned['plan_id'],
                    verified_at=_now(),verification=checked['verification'],classification_digest=digest(classification),
                    cohort_id=classification['cohort']['cohort_id'],
                    preparation_manifest=classification['preparation_manifest'],
                    validity='point_in_time_not_permanent_source_authorization')
                return {'research-cohort.json':canonical(classification['cohort']),
                        'classification-verification.json':canonical(verification)}
            publish_bundle(context=context,plan_id=planned['plan_id'],directory=output,
                kind='classification_export',build=build_classification_export)
            response_extra=dict(cohort_file=str(output/'research-cohort.json'),
                verification_file=str(output/'classification-verification.json'),classification_status=checked_export['status'])
        elif args.command=='export-review-evidence':
            from agc_runtime.metrics_host import load_host,output_directory
            from agc_runtime.metrics_review_batch import validate_review
            from agc_runtime.metrics_review_evidence import freeze_evidence,evidence_index
            from agc_runtime.metrics_capture_plan import capture_plan_resolver
            from agc_runtime.metrics_research_cohort import validate_research_cohort
            from agc_runtime.metrics_research_plan import research_plan_resolver
            from agc_runtime.metrics_execution import _write
            batch=validate_batch(_read_plan_input(args.batch))
            review=validate_review(_read_plan_input(args.review),batch)
            planned=review['plan']; context=load_host()
            output=output_directory(args.output,context,existing=False)
            execution=output_directory(args.execution_dir,context,existing=True)
            source_map=_read_plan_input(args.source_map)
            scenarios={c['scenario'] for c in planned['cases']}
            cohort=None
            if scenarios=={'research'} or (not scenarios and isinstance(source_map,dict)
                    and source_map.get('schema_version')=='agc.metrics-research-source-map.v1'):
                if args.cohort is None or args.references is None:
                    raise ValueError('research_evidence_sources_required')
                cohort=validate_research_cohort(batch,_read_plan_input(args.cohort))
                source=context['research_source_factory'](_read_plan_input(args.references))
                source.validate_cohort(cohort)
                resolver=research_plan_resolver(batch,cohort,planned,source_map,source=source)
            else:
                if 'research' in scenarios or args.cohort is not None or args.references is not None:
                    raise ValueError('evidence_source_kind_mismatch')
                resolver=capture_plan_resolver(planned,source_map,source=context['source'])
            from agc_runtime.metrics_report_artifacts import publish_bundle
            exported={}
            def build_evidence_export():
                for case in planned['cases']: resolver(case['case_id'])
                evidence=freeze_evidence(batch,review,execution,resolve_case=resolver,ledger_directory=context['ledger'],require_source_binding=True)
                index=evidence_index(batch,review,evidence)
                html=render_report(batch,review=review,evidence=evidence,research_cohort=cohort)
                for case in planned['cases']: resolver(case['case_id'])
                exported.update(evidence=evidence,index=index)
                return {'evidence-index.json':canonical(index),'report.html':html}
            publish_bundle(context=context,plan_id=planned['plan_id'],directory=output,
                kind='evidence_export',build=build_evidence_export)
            evidence,index=exported['evidence'],exported['index']
            response_extra=dict(evidence_file=str(output/'evidence-index.json'),report_file=str(output/'report.html'),
                                privacy=index['privacy'],
                                available_cases=sum(c['status']=='available' for c in evidence['cases']),
                                unavailable_cases=sum(c['status']=='unavailable' for c in evidence['cases']))
        elif args.command=='research-inputs':
            from agc_runtime.metrics_host import load_host
            from agc_runtime.metrics_research_inputs import prepare_research_inputs
            batch=validate_batch(_read_plan_input(args.batch))
            context=load_host()
            response_extra['research_preparation']=prepare_research_inputs(batch,_read_plan_input(args.references),
                source_factory=context['research_source_factory'])
        elif args.command == 'review':
            batch = validate_batch(_read_plan_input(args.batch))
            feedback = _read_plan_input(args.feedback)
            if not isinstance(feedback, dict) or set(feedback) != {'case_id','decision','correction','feedback_ref','timestamp'}:
                raise ValueError('feedback_fields_invalid')
            append_revision(batch, _read_plan_input(args.review), args.revisions_dir, **feedback)
        elif args.command == 'research-cohort':
            from agc_runtime.metrics_research_cohort import freeze_research_cohort
            from agc_runtime.metrics_evidence import _root
            from agc_runtime.metrics_execution import _write
            output=args.output.expanduser().absolute()
            _root(output.parent)
            if output.exists():
                raise ValueError('output_exists')
            batch=validate_batch(_read_plan_input(args.batch))
            value=freeze_research_cohort(batch,_read_plan_input(args.tasks),
                                        classifier=_read_plan_input(args.classifier))
            output.mkdir(exist_ok=False)
            _write(output/'research-cohort.json',value)
        elif args.command == 'plan':
            output = args.output.expanduser().resolve()
            if output.exists():
                raise ValueError('output_exists')
            batch = validate_batch(_read_plan_input(args.batch))
            value = prepare_plan(batch_id=batch['batch_id'],
                cases=_read_plan_input(args.cases),
                judge=_read_plan_input(args.judge),
                rules=_read_plan_input(args.rules))
            output.mkdir(parents=True, exist_ok=False)
            with (output / 'plan.json').open('x', encoding='utf-8', newline='\n') as handle:
                handle.write(canonical(value))
        else:
            batch = validate_batch(_read_plan_input(args.batch))
            review = _read_plan_input(args.review) if args.review else None
            research_cohort=_read_plan_input(args.research_cohort) if args.research_cohort else None
            research_preparation=_read_plan_input(args.research_preparation) if args.research_preparation else None
            evidence=_read_plan_input(args.evidence) if args.evidence else None
            html = render_report(batch, review=review, revisions_dir=args.revisions_dir,
                                 research_cohort=research_cohort,research_preparation=research_preparation,evidence=evidence)
            with args.output.open('x', encoding='utf-8', newline='\n') as handle:
                handle.write(html)
        print(canonical(dict(status='ok', batch_id=batch['batch_id'], model_called=model_called,**response_extra)))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
        print(canonical(dict(status='error', code='metrics_operation_failed', model_called=model_called)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
