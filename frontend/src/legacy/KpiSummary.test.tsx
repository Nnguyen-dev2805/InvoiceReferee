import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { KpiSummary } from './KpiSummary';
import { caseRecord, completedRun } from './testBuilders';
import type { RunRecord } from './types';

describe('KpiSummary', () => {
  it('computes pending queue count for current role correctly', () => {
    const case1 = caseRecord({ id: 'c1', open_owner_modes: ['REVIEWER'] });
    const case2 = caseRecord({ id: 'c2', open_owner_modes: ['REVIEWER', 'APPROVER'] });
    const case3 = caseRecord({ id: 'c3', open_owner_modes: ['EMPLOYEE'] });

    const { rerender } = render(
      <KpiSummary
        cases={[case1, case2, case3]}
        role="REVIEWER"
        runsByCase={{}}
      />,
    );

    // Reviewer has 2 pending cases (c1 and c2)
    expect(screen.getByText(/hồ sơ chờ.*kế toán/i)).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();

    rerender(
      <KpiSummary
        cases={[case1, case2, case3]}
        role="EMPLOYEE"
        runsByCase={{}}
      />,
    );

    // Employee has 1 pending case (c3)
    expect(screen.getByText(/hồ sơ chờ.*nhân viên/i)).toBeTruthy();
    expect(screen.getByText('1')).toBeTruthy();
  });

  it('calculates total pending approval VND amount', () => {
    const case1 = caseRecord({
      id: 'c1',
      workflow_state: 'WAITING_APPROVAL',
      claim: {
        employee_id: 'emp1',
        profile: 'TRAVEL',
        purpose_type: 'BUSINESS',
        purpose: 'trip',
        trip: 'HN',
        requested_amount_vnd: 1_500_000,
        payer_type: 'PERSONAL',
        received_full: true,
      },
    });

    const case2 = caseRecord({
      id: 'c2',
      workflow_state: 'WAITING_APPROVAL',
      claim: {
        employee_id: 'emp2',
        profile: 'CLIENT_MEAL',
        purpose_type: 'BUSINESS',
        purpose: 'dinner',
        trip: 'HCM',
        requested_amount_vnd: 2_500_000,
        payer_type: 'PERSONAL',
        received_full: true,
      },
    });

    render(
      <KpiSummary
        cases={[case1, case2]}
        role="APPROVER"
        runsByCase={{}}
      />,
    );

    // Total = 1,500,000 + 2,500,000 = 4,000,000 VND
    expect(screen.getByText('4.000.000₫')).toBeTruthy();
    expect(screen.getByText('2 hồ sơ đủ điều kiện')).toBeTruthy();
  });

  it('displays routine auto completion rate from runs', () => {
    const run1: RunRecord = completedRun(); // completion_basis: 'ROUTINE_AUTO'
    const run2: RunRecord = {
      ...completedRun(),
      id: 'run-2',
      result: {
        ...completedRun().result!,
        decision: {
          ...completedRun().result!.decision,
          completion_basis: 'HUMAN_AUTHORIZED',
        },
      },
    };

    render(
      <KpiSummary
        cases={[]}
        role="REVIEWER"
        runsByCase={{ 'run-1': run1, 'run-2': run2 }}
      />,
    );

    // 1 routine auto out of 2 completed = 50%
    expect(screen.getByText('50%')).toBeTruthy();
    expect(screen.getByText('1/2 lượt tự động')).toBeTruthy();
  });
});
