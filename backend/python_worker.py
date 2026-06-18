"""
Persistent Python worker for Node.js backend routes.

Stays alive for the lifetime of the Node process. Reads newline-delimited JSON
requests from stdin, dispatches to the appropriate Python function, writes
newline-delimited JSON responses to stdout.

Protocol:
  IN:  {"id": "<uuid>", "op": "<operation>", "args": {...}, "timeout": <ms>}
  OUT: {"id": "<uuid>", "result": {...}}
       {"id": "<uuid>", "error": "<message>"}

One request per line, one response per line. Requests are processed serially
(single-threaded) — safe because SQLite has its own locking and all operations
are short-lived except demo generation and pitch (which have their own timeouts).
"""
import json
import os
import sys
import traceback

# ── Path setup (same as the old pyCall preamble) ─────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNTIME   = os.path.join(_REPO_ROOT, 'runtime')
_AI_HOME   = os.environ.get('AI_EMPLOYEE_HOME') or os.environ.get('AI_HOME') or \
             os.path.join(os.path.expanduser('~'), '.ai-employee')

sys.path.insert(0, _RUNTIME)
os.environ.setdefault('AI_HOME', _AI_HOME)

# ── Lazy module cache — import on first use, stay imported ───────────────────
_mods: dict = {}

def _mod(name: str):
    if name not in _mods:
        _mods[name] = __import__(name, fromlist=[''])
    return _mods[name]


# ── Operation dispatch table ──────────────────────────────────────────────────

def _dispatch(op: str, args: dict):
    # ── orders ────────────────────────────────────────────────────────────────
    if op == 'orders.list':
        m = _mod('core.orders_store')
        status = args.get('status') or None
        orders = m.orders_ophalen(status=status) if status else m.orders_ophalen()
        return {'ok': True, 'orders': orders}

    if op == 'orders.get':
        m = _mod('core.orders_store')
        result = m.order_ophalen(args['id'])
        return result if result else None

    if op == 'orders.create':
        m = _mod('core.orders_store')
        return m.order_aanmaken(
            bedrijfsnaam=args['bedrijfsnaam'],
            plaats=args['plaats'],
            branche=args['branche'],
            contact=args.get('contact', ''),
            prijs=float(args.get('prijs', 299)),
        )

    if op == 'orders.delete':
        m = _mod('core.orders_store')
        return m.order_verwijderen(args['id'])

    if op == 'orders.approve':
        store = _mod('core.orders_store')
        order = store.order_ophalen(args['id'])
        if not order:
            return {'ok': False, 'error': 'Order niet gevonden'}
        if order['status'] not in ('ter_review', 'demo_klaar'):
            return {'ok': False, 'error': f"Verwacht status ter_review/demo_klaar, is: {order['status']}"}
        return {'ok': True, 'order': store.status_bijwerken(args['id'], 'goedgekeurd')}

    if op == 'orders.research':
        store  = _mod('core.orders_store')
        res_m  = _mod('core.bedrijf_research')
        order  = store.order_ophalen(args['id'])
        if not order:
            return {'ok': False, 'error': 'Order niet gevonden'}
        data = res_m.research_bedrijf(order['bedrijfsnaam'], order['plaats'])
        try:
            import json as _json
            with store._conn() as conn:
                conn.execute(
                    'UPDATE orders SET research_data=? WHERE id=?',
                    (_json.dumps(data, ensure_ascii=False), args['id']),
                )
        except Exception:
            pass
        return {'ok': True, 'research_data': data}

    if op == 'orders.research_data':
        # Persist arbitrary research_data dict onto an order (used by Finder)
        store = _mod('core.orders_store')
        import json as _json
        try:
            with store._conn() as conn:
                conn.execute(
                    'UPDATE orders SET research_data=? WHERE id=?',
                    (_json.dumps(args['research_data'], ensure_ascii=False), args['id']),
                )
            return {'ok': True}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    if op == 'orders.demo':
        store = _mod('core.orders_store')
        gen_m = _mod('core.demo_generator')
        order = store.order_ophalen(args['id'])
        if not order:
            return {'ok': False, 'error': 'Order niet gevonden'}
        gen = gen_m.genereer_demo(
            bedrijfsnaam=order['bedrijfsnaam'],
            plaats=order['plaats'],
            branche=order['branche'],
            diensten=None,
        )
        if gen['status'] == 'ok':
            store.status_bijwerken(args['id'], 'demo_klaar', demo_pad=gen['path'])
            updated = store.status_bijwerken(args['id'], 'ter_review')
            return {'ok': True, 'order': updated, 'demo_pad': gen['path'], 'bytes': gen['bytes']}
        return {'ok': False, 'error': gen.get('error', 'Generatie mislukt')}

    if op == 'orders.pitch':
        m = _mod('core.pitch')
        return m.genereer_pitch(args['id'], demo_url=args.get('demo_url', ''))

    if op == 'orders.akkoord':
        m = _mod('core.pitch')
        return m.markeer_akkoord(args['id'])

    if op == 'orders.status':
        m = _mod('core.pitch')
        fn_map = {
            'gepitcht': m.markeer_gepitcht,
            'betaald':  m.markeer_betaald,
            'live':     m.markeer_live,
        }
        fn = fn_map.get(args['status'])
        if not fn:
            return {'ok': False, 'error': f"Ongeldig status: {args['status']}"}
        return fn(args['id'])

    if op == 'orders.deploy':
        m = _mod('core.hosting')
        return m.deploy_to_netlify(args['id'])

    if op == 'orders.search':
        m = _mod('core.bedrijf_finder')
        return m.zoek_bedrijven(args['stad'], args['branche'], int(args.get('aantal', 8)))

    if op == 'orders.hosting_status':
        return {'has_token': bool(os.environ.get('NETLIFY_API_TOKEN', ''))}

    if op == 'orders.betaald':
        m = _mod('core.pitch')
        return m.markeer_betaald(args['id'], args.get('referentie', ''))

    if op == 'orders.update':
        m = _mod('core.orders_store')
        return m.order_bijwerken(
            args['id'],
            bedrijfsnaam=args.get('bedrijfsnaam'),
            plaats=args.get('plaats'),
            branche=args.get('branche'),
            contact=args.get('contact'),
            prijs=(float(args['prijs']) if args.get('prijs') is not None else None),
        )

    if op == 'orders.stuur_link':
        m = _mod('core.pitch')
        return m.genereer_deel_links(args['id'], base_url=args.get('base_url', ''))

    if op == 'orders.demo_quality':
        m = _mod('core.demo_quality_gate')
        return m.evaluate_order_demo(args['id'])

    if op == 'orders.resource_plan':
        m = _mod('core.orders_forge_handoff')
        return m.build_resource_plan(args['id'])

    if op == 'orders.forge_handoff':
        m = _mod('core.orders_forge_handoff')
        return m.create_forge_project_from_order(
            args['id'],
            base_url=args.get('base_url', ''),
            override_payment=bool(args.get('override_payment', False)),
        )

    # ── ecom ──────────────────────────────────────────────────────────────────
    if op == 'ecom.research':
        m = _mod('core.product_researcher')
        return m.research_products(
            args['niche'],
            args.get('markt', 'nl'),
            int(args.get('min_marge', 30)),
        )

    if op == 'ecom.scout':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        agent_m = _mod('ecom_agent')
        # ProductScoutAgent if available, else fallback
        try:
            from agents.product_scout.product_scout import ProductScoutAgent
            agent = ProductScoutAgent()
            return agent.execute({
                'markt': args.get('markt', 'nl'),
                'min_marge': int(args.get('min_marge', 30)),
            })
        except ImportError:
            return {'ok': False, 'error': 'ProductScoutAgent not found'}

    if op == 'ecom.listing.create':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.genereer_en_sla_op(args['product_naam'], platform=args.get('platform', 'shopify'))

    if op == 'ecom.listing.get':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.haal_listing_op(args['id'])

    if op == 'ecom.listing.update':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.werk_listing_bij(args['id'], args.get('updates', {}))

    if op == 'ecom.listing.list':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.lijst_listings()

    if op == 'ecom.listing.optimize':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.optimaliseer_listing(args['id'])

    if op == 'ecom.listing.publish':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.publiceer_listing(args['id'], platform=args.get('platform', 'shopify'))

    # ── ecom listing store (core.ecom_listing_store) ──────────────────────────
    if op == 'ecom.listing.list':
        m = _mod('core.ecom_listing_store')
        status = args.get('status') or None
        listings = m.listings_ophalen(status=status) if status else m.listings_ophalen()
        return listings

    if op == 'ecom.listing.get':
        m = _mod('core.ecom_listing_store')
        return m.listing_ophalen(args['id'])

    if op == 'ecom.listing.update':
        m = _mod('core.ecom_listing_store')
        velden = {k: v for k, v in args.items() if k != 'id'}
        return m.listing_bijwerken(args['id'], **velden)

    if op == 'ecom.listing.approve':
        m = _mod('core.ecom_listing_store')
        listing = m.listing_ophalen(args['id'])
        if not listing or (isinstance(listing, dict) and listing.get('ok') is False):
            return {'ok': False, 'error': 'Listing niet gevonden'}
        if listing.get('status') == 'gepubliceerd':
            return {'ok': False, 'error': 'Listing is al gepubliceerd'}
        return m.listing_status_bijwerken(args['id'], 'goedgekeurd')

    if op == 'ecom.listing.delete':
        m = _mod('core.ecom_listing_store')
        return m.listing_verwijderen(args['id'])

    if op == 'ecom.listing.emails':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.genereer_email_flow_en_sla_op(args['id'], args.get('type', 'welcome'))

    if op == 'ecom.listing.ads':
        _AGENT_DIR = os.path.join(_REPO_ROOT, 'runtime', 'agents', 'ecom-agent')
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)
        m = _mod('ecom_agent')
        return m.genereer_ads_en_sla_op(args['id'])

    # ── companion (conversation runtime + capability registry) ──────────────────
    if op == 'companion.message':
        m = _mod('companion.conversation_runtime')
        return m.handle_message(args)

    if op == 'companion.capabilities':
        m = _mod('companion.capability_registry')
        return {'capabilities': m.get_capability_registry().to_dicts()}

    # ── service control / compute routing visibility (P9) ───────────────────────
    if op == 'lanes.status':
        lanes = _mod('core.model_lanes')
        try:
            budget = _mod('engine.compute.resource_manager').get_resource_manager().to_dict()
        except Exception:
            budget = None
        return {
            'ok': True,
            'tiers': lanes.tier_models(),
            'upgrades': {t: lanes.upgrade_options(t) for t in ('CODE', 'HEAVY', 'DEEP_THINKING')},
            'budget': budget,
        }

    # ── evolution (offline learning engine — controller.handle_evolution_op) ─────
    # Controller supports exactly: status / traces / lessons / candidates /
    # promote / rollback. We expose only those; no invented ops.
    if op == 'evolution.status':
        return _mod('evolution.controller').get_evolution_controller().handle_evolution_op('status', args)

    if op == 'evolution.traces':
        return _mod('evolution.controller').get_evolution_controller().handle_evolution_op('traces', args)

    if op == 'evolution.lessons':
        return _mod('evolution.controller').get_evolution_controller().handle_evolution_op('lessons', args)

    if op == 'evolution.candidates':
        return _mod('evolution.controller').get_evolution_controller().handle_evolution_op('candidates', args)

    if op == 'evolution.candidate_promote':
        return _mod('evolution.controller').get_evolution_controller().handle_evolution_op('promote', args)

    if op == 'evolution.candidate_rollback':
        return _mod('evolution.controller').get_evolution_controller().handle_evolution_op('rollback', args)

    # ── work engine (Module 4 — acquisition + delivery lifecycle) ───────────────
    # All money figures are labelled estimates; quote + deliver are HITL-gated.
    if op == 'work.ingest':
        eng = _mod('money.work_engine').get_work_engine()
        return eng.ingest_opportunity(args.get('opportunity') or args)

    if op == 'work.list':
        eng = _mod('money.work_engine').get_work_engine()
        return eng.list_opportunities(args.get('status') or None)

    if op == 'work.get':
        eng = _mod('money.work_engine').get_work_engine()
        return eng.get_opportunity(args['id'])

    if op == 'work.evaluate':
        eng = _mod('money.work_engine').get_work_engine()
        return eng.evaluate(args['id'], use_llm=bool(args.get('use_llm', True)))

    if op == 'work.quote':
        eng = _mod('money.work_engine').get_work_engine()
        return eng.quote(args['id'], submitted_by=args.get('submitted_by', 'work-engine'))

    if op == 'work.deliver':
        eng = _mod('money.work_engine').get_work_engine()
        return eng.deliver(args['id'], submitted_by=args.get('submitted_by', 'work-engine'))

    # ── CompanyOS (P10) — validate-before-build company lifecycle ──
    if op == 'company.start':
        cos = _mod('companyos').get_companyos()
        return cos.start_company(name=args.get('name') or 'Untitled', idea=args.get('idea') or '',
                                 answers=args.get('answers') if isinstance(args.get('answers'), dict) else None)

    if op == 'company.validate':
        cos = _mod('companyos').get_companyos()
        return cos.validate_company(args['id'])

    if op == 'company.refine':
        cos = _mod('companyos').get_companyos()
        return cos.refine_idea(args.get('idea') or '')

    if op == 'company.build':
        cos = _mod('companyos').get_companyos()
        return cos.begin_build(args['id'], override=bool(args.get('override')),
                               override_reason=str(args.get('override_reason') or ''))

    if op == 'company.plan':
        cos = _mod('companyos').get_companyos()
        return cos.plan_company(args['id'])

    if op == 'company.cycle':
        cos = _mod('companyos').get_companyos()
        return cos.run_company_cycle(args['id'])

    if op == 'company.export':
        cos = _mod('companyos').get_companyos()
        return cos.export_company(args['id'])

    if op == 'company.get':
        cos = _mod('companyos').get_companyos()
        return cos.get_company(args['id'])

    if op == 'company.list':
        cos = _mod('companyos').get_companyos()
        return cos.list_companies()

    raise ValueError(f'Unknown op: {op}')


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    # Flush stdout after every write so Node sees responses immediately.
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        req_id = '?'
        try:
            req = json.loads(raw_line)
            req_id = req.get('id', '?')
            op     = req.get('op', '')
            args   = req.get('args', {})
            result = _dispatch(op, args)
            print(json.dumps({'id': req_id, 'result': result}), flush=True)
        except Exception as exc:
            tb = traceback.format_exc()
            print(json.dumps({'id': req_id, 'error': str(exc), 'trace': tb[-500:]}), flush=True)


if __name__ == '__main__':
    main()
