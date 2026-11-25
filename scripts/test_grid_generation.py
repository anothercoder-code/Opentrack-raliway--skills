"""Offline compiler tests. Synthetic receipts are test doubles, not native evidence."""
import copy
import unittest
import grid_generation as g


def test_receipts(plan):
    """Generate deliberately nonsequential test IDs; never persisted as delivery evidence."""
    n=37; vertices={}; changes=[]
    for batch in plan['geometry_batches']:
        for x in batch['changes']:
            n+=19
            if x['kind']=='create_vertex':
                vertices[x['vertex_key']]=[n,n+7]
                changes.append({'kind':'create_vertex','document':g.DOCUMENT,'vertex_key':x['vertex_key'],'end_ids':[n,n+7]})
            elif x['kind']=='create_edge':
                changes.append({'kind':'create_edge','document':g.DOCUMENT,'edge_id':n,'end_ids':[vertices[x[k]['vertex_key']][x[k]['side']] for k in ('first','second')],'length_m':x['length_m']})
            elif x['kind']=='create_signal':
                changes.append({'kind':'create_signal','document':g.DOCUMENT,'end_id':vertices[x['end']['vertex_key']][x['end']['side']],'signal_id':n})
    return [{'changes':changes}]


class GridCompilerTests(unittest.TestCase):
    def setUp(self): self.plan=g.build_plan()
    def reject(self, mutation):
        mutation(self.plan)
        with self.assertRaises((ValueError,KeyError)): g.validate_structure(self.plan)
    def test_no_batches(self): self.reject(lambda p:p.update(geometry_batches=[]))
    def test_partial_batches(self): self.reject(lambda p:p.update(geometry_batches=p['geometry_batches'][:1]))
    def test_signal_system_drift(self): self.reject(lambda p:p['geometry_batches'][0]['changes'][-1].update(main_signal_type=0))
    def test_terminal_station_drift(self): self.reject(lambda p:p['tracks'][0]['stations'].update(H1_T0=p['tracks'][0]['stations']['H1_T4']))
    def test_real_schema_and_structure(self): self.assertTrue(g.validate_structure(self.plan)['valid'])
    def test_broken_half_link(self): self.reject(lambda p:p['tracks'][0]['edges'][0]['first'].update(side=0))
    def test_bad_length(self): self.reject(lambda p:p['tracks'][0]['edges'][0].update(length_m=1))
    def test_duplicate_vertex(self): self.reject(lambda p:p['tracks'][0]['vertices'].__setitem__(1,p['tracks'][0]['vertices'][0]))
    def test_missing_crossing_direction(self): self.reject(lambda p:p['crossings']['J11'].pop())
    def test_wrong_crossing(self): self.reject(lambda p:p['crossings']['J11'].__setitem__(0,'H1_F_E6'))
    def test_wrong_travel_direction(self): self.reject(lambda p:p['tracks'][0]['travel_vertices'].reverse())
    def test_missing_geometry_edge(self): self.reject(lambda p:p['geometry_batches'][0]['changes'].pop(14))
    def test_payload_geometry_drift(self): self.reject(lambda p:p['geometry_batches'][0]['changes'][14].update(length_m=10))
    def test_signal_direction(self): self.reject(lambda p:p['geometry_batches'][0]['changes'][-1]['end'].update(side=1))
    def test_wrong_direction_speed(self): self.reject(lambda p:p['geometry_batches'][0]['changes'][14]['speeds'][0].update(reverse_kmh=120))
    def test_platform_inside_crossing(self): self.reject(lambda p:p['tracks'][0]['stations']['H1_S1'].update(vertex_key='H1_F_N3'))
    def test_midnight_boundary(self): self.reject(lambda p:p['scenario']['courses'][-1]['stops'][-1].update(arrival_s=86400,departure_s=86400))
    def test_timetable_dwell(self): self.reject(lambda p:p['scenario']['courses'][0]['stops'][1].update(departure_s=539))
    def test_native_completion_claim(self): self.reject(lambda p:p.update(native_simulation_verified=True))
    def test_binding_requires_actual_receipt_shape(self):
        with self.assertRaises(ValueError):g.bind(self.plan,[{'session_id':'not-a-manifest'}],'p','r','TEST_SPEED')
    def test_binding_rejects_missing_edge(self):
        receipts=test_receipts(self.plan);receipts[0]['changes']=[x for x in receipts[0]['changes'] if x['kind']!='create_edge']
        with self.assertRaises(ValueError):g.bind(self.plan,receipts,'p','r','TEST_SPEED')
    def test_binding_rejects_duplicate_ids(self):
        receipts=test_receipts(self.plan);rows=[x for x in receipts[0]['changes'] if x['kind']=='create_vertex'];rows[1]['end_ids']=rows[0]['end_ids']
        with self.assertRaises(ValueError):g.bind(self.plan,receipts,'p','r','TEST_SPEED')
    def test_binding_rejects_duplicate_edge_ids(self):
        receipts=test_receipts(self.plan)
        for r in receipts[0]['changes']:
            if r['kind']=='create_edge':r['edge_id']=999999
        with self.assertRaises(ValueError):g.bind(self.plan,receipts,'p','r','TEST_SPEED')
    def test_binding_rejects_duplicate_signal_ids(self):
        receipts=test_receipts(self.plan)
        for r in receipts[0]['changes']:
            if r['kind']=='create_signal':r['signal_id']=999999
        with self.assertRaises(ValueError):g.bind(self.plan,receipts,'p','r','TEST_SPEED')
    def test_binding_rejects_bool_id(self):
        receipts=test_receipts(self.plan);receipts[0]['changes'][0]['end_ids'][0]=True
        with self.assertRaises(ValueError):g.bind(self.plan,receipts,'p','r','TEST_SPEED')
    def test_binding_real_schemas_and_path_references(self):
        result=g.bind(self.plan,test_receipts(self.plan),'TEST_ONLY_PROJECT','TEST_ONLY_RUN','TEST_ONLY_SPEED')
        batches=result['generation_batches'];routes={r['name']:r for b in batches for r in b.get('routes',[])}
        self.assertEqual(len(routes),156);self.assertEqual(len(batches),7)
        paths={p['name']:p for b in batches for p in b.get('paths',[])}
        itineraries={i['name']:i for b in batches for i in b.get('itineraries',[])}
        for path in paths.values():
            chain=[routes[r['name']] for r in path['routes']]
            for a,b in zip(chain,chain[1:]):self.assertEqual(a['nodes'][-1],b['nodes'][0])
            for ref,r in zip(path['routes'],chain):self.assertEqual(ref['start_id'],r['nodes'][0]['end_id'])
        for i in itineraries.values():self.assertTrue(all(p in paths for p in i['paths']))
        courses=[c for b in batches for c in b.get('courses',[])]
        self.assertEqual([c['course_id'] for c in courses],[c['course_id'] for c in self.plan['scenario']['courses']])
        self.assertTrue(all(c['itineraries'][0] in itineraries for c in courses))
        self.assertEqual(len(courses),288)
        for merge in result['safety_changes']:self.assertEqual(len(set(merge['edge_ids'])),4)
        self.assertFalse(result['native_simulation_verified'])
    def test_editor_real_schema(self):
        # Schema-only fixture, not an actual session or evidence.
        result=g.editor_payload(self.plan['geometry_batches'][0],'editor-'+'a'*16,0)
        self.assertEqual(len(result['changes']),41)

if __name__=='__main__':unittest.main()
