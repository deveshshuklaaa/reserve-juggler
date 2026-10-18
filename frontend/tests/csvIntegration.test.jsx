import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { SimulationProvider } from '../src/context/SimulationContext';
import { createRealApi } from '../src/api/treasuryApi';
import { createMockApi } from '../src/api/mockTreasuryApi';
import { AppRoutes } from '../src/App';
import { ORGANIZER_HEADERS } from '../src/utils/organizerCsv';

vi.mock('../src/components/Charts', () => ({ TimeChart: () => <div />, ComparisonBars: () => <div /> }));
afterEach(() => vi.unstubAllGlobals());
const raw = [ORGANIZER_HEADERS.join(','),
  '2026-02-01 00:00:00,1000,500,500,False,False,4,5,100,2,5000,18,0.5,2,15,12',
  '2026-02-01 01:00:00,1200,600,600,False,False,4,5,100,2,5000,18,0.5,2,15,12'].join('\n');
function mount(api) {
  render(<MemoryRouter initialEntries={['/command-center']}><SimulationProvider api={api}><AppRoutes /></SimulationProvider></MemoryRouter>);
  return userEvent.setup();
}

describe('live organizer CSV workflow', () => {
  it('previews locally and sends the original CSV only after explicit start', async () => {
    const api = createMockApi({ latency: 0 }); api.mode = 'real';
    api.createRunFromOrganizer = vi.fn(async () => api.createRun({}));
    const user = mount(api);
    await user.click(screen.getByRole('button', {name: 'Import cash flows'}));
    await user.upload(screen.getByLabelText('Cash flow CSV file'), new File([raw], 'organizer.csv', {type:'text/csv'}));
    await screen.findByText('organizer.csv');
    expect(api.createRunFromOrganizer).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name:'Start CSV simulation'})).toBeEnabled();
    await user.click(screen.getByRole('button', {name:'Start CSV simulation'}));
    await screen.findByRole('button', {name:'Advance one step'});
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.createRunFromOrganizer).toHaveBeenCalledWith(expect.objectContaining({format:'organizer',csv_text:raw}), expect.objectContaining({signal:expect.any(AbortSignal)}));
  });
  it('keeps a failed import retryable without a generated fallback', async () => {
    const api=createMockApi({latency:0}); api.mode='real';
    api.createRunFromOrganizer=vi.fn().mockRejectedValueOnce(new Error('Import failed.')).mockImplementationOnce(()=>api.createRun({}));
    const generated=vi.spyOn(api,'createRun'); const user=mount(api);
    await user.click(screen.getByRole('button',{name:'Import cash flows'}));
    await user.upload(screen.getByLabelText('Cash flow CSV file'),new File([raw],'retry.csv',{type:'text/csv'}));
    await screen.findByText('retry.csv');
    await user.click(screen.getByRole('button',{name:'Start CSV simulation'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Start CSV simulation'})).toBeEnabled());
    expect(generated).not.toHaveBeenCalled(); expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'Start CSV simulation'}));
    await screen.findByRole('button',{name:'Advance one step'});
    expect(api.createRunFromOrganizer).toHaveBeenCalledTimes(2);
  });
  it('posts exact CSV bytes as text/csv and binds the run to its returned dataset', async () => {
    const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({dataset_id:'uploaded:hash',row_count:3500}),{status:201}))
      .mockResolvedValueOnce(new Response(JSON.stringify({run_id:'uploaded-run'}),{status:201}));
    vi.stubGlobal('fetch',fetch); await createRealApi().createRunFromOrganizer({csv_text:raw});
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/datasets');
    expect(fetch.mock.calls[0][1]).toMatchObject({body:raw,headers:{'Content-Type':'text/csv'}});
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({dataset_id:'uploaded:hash',duration_steps:3500,initial_cash_cents:2000000000});
  });
  it('does not create a run after server validation failure', async () => {
    const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({error_code:'INVALID_DATASET',message:'Row 2: invalid source flag'}),{status:422}));
    vi.stubGlobal('fetch',fetch);
    await expect(createRealApi().createRunFromOrganizer({csv_text:raw})).rejects.toMatchObject({status:422,message:'Row 2: invalid source flag'});
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('keeps comparisons on the uploaded dataset without the January fallback', async () => {
    const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({run_id:'parent'}))).mockResolvedValueOnce(new Response(JSON.stringify({results:[]})));
    vi.stubGlobal('fetch',fetch); await createRealApi().runBacktest('live',{days:7,source_dataset:{dataset_id:'uploaded:hash'}});
    const body=JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.dataset_id).toBe('uploaded:hash'); expect(body.start_time).toBeUndefined();
  });
});
