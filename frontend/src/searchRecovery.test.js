import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {SearchResults} from './components/SearchResults.jsx';

test('archive outage preserves the query and offers explicitly local real datasets without fabricated results',()=>{
  const html=renderToStaticMarkup(React.createElement(SearchResults,{mode:'live',onSearchLocal:()=>{},search:{status:'error',query:{ra_deg:269.45,dec_deg:4.69,fov_arcmin:2},error:{code:'upstream_http_error',message:'IRSA unavailable',details:{upstream_status:502}}}}));
  assert.match(html,/IRSA archive search is temporarily unavailable/);
  assert.match(html,/do not need to restart/);assert.match(html,/RA 269.45/);
  assert.match(html,/href="\/processing\/"/);assert.match(html,/target="_blank"/);
  assert.match(html,/Open real imported FITS datasets/);assert.match(html,/No fixture has been substituted/);
  assert.doesNotMatch(html,/observation-row/);
  assert.match(html,/Search downloaded observations/);
});

test('local empty search explains its limited coverage and offers live retry',()=>{
  const html=renderToStaticMarkup(React.createElement(SearchResults,{mode:'live',search:{status:'empty',source:'local',result:{observations:[],warnings:[],coverage_summary:{source:'imported-local',complete:false}}}}));
  assert.match(html,/Downloaded real observations/);
  assert.match(html,/No downloaded observations cover/);
  assert.match(html,/Try live archive/);
  assert.doesNotMatch(html,/No observations found for this query/);
});

test('an empty partial response never claims complete absence of observations',()=>{
  const html=renderToStaticMarkup(React.createElement(SearchResults,{mode:'live',search:{status:'empty',result:{observations:[],warnings:[],coverage_summary:{collections_failed:[{collection:'spherex_qr3',upstream_status:502}]}}}}));
  assert.match(html,/Archive coverage is incomplete/);
  assert.doesNotMatch(html,/No observations found for this query/);
});
