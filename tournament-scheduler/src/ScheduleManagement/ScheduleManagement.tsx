import React, { useState, useEffect } from 'react';

import { createDefaultSchedule, Schedule, ScheduleDto } from '../models/Schedule';
import User from '../models/User';
import { Card, CardContent, CardActions, Button, makeStyles, Theme, Container } from '@material-ui/core';
import { Styles } from '@material-ui/core/styles/withStyles';
import { ScheduleWizard } from './ScheduleWizard'

const getSchedules = () =>
  fetch(`${window.process.env.REACT_APP_BASE_URL}/api/schedules`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'Authorization': `Bearer: ${localStorage.getItem('jwtToken')}`,
    },
  })
    .then(res => res.status >= 400 && res.status < 600
      ? Promise.reject(Error(res.status.toString()))
      : res)
    .then(res =>
      res.json().then((scheduleDtos: ScheduleDto[] | undefined) =>
        scheduleDtos?.map(scheduleDto => new Schedule(scheduleDto))))

const postSchedules = (schedule: ScheduleDto) =>
  fetch(`${window.process.env.REACT_APP_BASE_URL}/api/schedules`, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'Authorization': `Bearer: ${localStorage.getItem('jwtToken')}`,
    },
    body: JSON.stringify(schedule),
  })
    .then(res => res.status >= 400 && res.status < 600
      ? Promise.reject(Error(res.status.toString()))
      : res)
    .then(res => res.json().then((_newScheduleId: number) => { }))

const putSchedule = (schedule: ScheduleDto) =>
  fetch(`${window.process.env.REACT_APP_BASE_URL}/api/schedules/${schedule.id}`, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'Authorization': `Bearer: ${localStorage.getItem('jwtToken')}`,
    },
    body: JSON.stringify(schedule),
  }).then(res => res.json().then((_newScheduleId: number) => { }))

type ScheduleManagementProps = {
  currentUser: User
}

const ScheduleManagement: React.FC<ScheduleManagementProps> = (props: ScheduleManagementProps) => {
  const [schedules, setSchedules] = useState<Schedule[] | undefined>(undefined)
  const [currentSchedule, setCurrentSchedule] = useState<Schedule | undefined>(undefined)

  const editSchedule = (schedule?: Schedule) => {
    setCurrentSchedule(schedule)
  }

  const handleSave = (schedule: ScheduleDto) => {
    const savePromise = schedule.id === -1
      ? postSchedules(schedule)
      : putSchedule(schedule)
    savePromise
      .then(() => { console.log('test'); setCurrentSchedule(undefined) })
      .catch(console.error)
  }

  useEffect(() => {
    getSchedules()
      .then((res: Schedule[] | undefined) => {
        console.log(res)
        setSchedules(res)
      })
  }, [])

  const styles = {
    card: {
      width: '100%',
      textAlign: 'start',
      marginTop: '16px',
      marginBottom: '16px',
    },
    cardActions: {
      display: 'flex',
    },
  }
  const classes = makeStyles((styles as Styles<Theme, {}, "card" | "cardActions">))()

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(
      () => console.log('text copied to clipboard successfully'),
      (err) => console.error(err),
    )
  }

  return currentSchedule
    ? <ScheduleWizard
      schedule={currentSchedule}
      onSave={handleSave}
      onCancel={() => setCurrentSchedule(undefined)}
    />
    : <Container>
      <div>
        Welcome '{props.currentUser.name}' ! This is where you can manage your schedule forms
      </div>

      <Button
        style={{ marginTop: styles.card.marginTop, width: styles.card.width }}
        variant="contained"
        color="primary"
        onClick={() => editSchedule(createDefaultSchedule())}
      >
        Create new Schedule
        </Button>
      {schedules && schedules.map(schedule =>
        <Card className={classes.card} key={schedule.id}>
          <CardContent>
            {schedule.name}
          </CardContent>
          <CardActions className={classes.cardActions}>
            <Button
              size="small"
              onClick={() => editSchedule(schedule)}
            >
              Edit
            </Button>
            <Button
              size="small"
              onClick={() => copyToClipboard(`${schedule.registrationLink}`)}
            >
              Copy registration link
            </Button>
          </CardActions>
        </Card>
      )}
    </Container>
}

export default ScheduleManagement;