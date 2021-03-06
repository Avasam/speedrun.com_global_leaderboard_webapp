import 'react-add-to-calendar/dist/react-add-to-calendar.min.css'

import DateFnsUtils from '@date-io/moment'
import { Container, createStyles, List, ListItem, ListItemText, makeStyles } from '@material-ui/core'
import { StatusCodes } from 'http-status-codes'
import moment from 'moment'
import type { FC } from 'react'
import { useEffect, useState } from 'react'
import AddToCalendar from 'react-add-to-calendar'

import { apiGet } from '../fetchers/Api'
import type { ScheduleDto } from '../models/Schedule'
import { Schedule } from '../models/Schedule'
import { TimeSlot } from '../models/TimeSlot'
import math from '../utils/Math'

type ScheduleRegistrationProps = {
  scheduleId: number
}

const useStyles = makeStyles(theme =>
  createStyles({
    root: {
      backgroundColor: theme.palette.background.paper,
      margin: theme.spacing(math.HALF),
    },
    rootHeader: {
      color: theme.palette.text.primary,
      fontWeight: theme.typography.fontWeightBold,
      backgroundColor: theme.palette.background.default,
      paddingTop: theme.spacing(math.HALF),
      paddingBottom: theme.spacing(math.HALF),
      paddingLeft: theme.spacing(2),
      paddingRight: theme.spacing(2),
    },
    nested: {
      paddingLeft: theme.spacing(2),
      paddingRight: theme.spacing(2),
    },
    item: {
      paddingTop: 0,
      paddingBottom: 0,
    },
    addToCalendar: {
      // eslint-disable-next-line @typescript-eslint/no-magic-numbers
      marginTop: theme.spacing(1.25),
      marginLeft: theme.spacing(2),
      marginBottom: 10,
      display: 'inline-block',
      color: theme.palette.text.primary,
      backgroundColor: theme.palette.background.default,
    },
  }))

const getSchedule = (id: number) =>
  apiGet(`schedules/${id}`)
    .then(res =>
      res.json().then((scheduleDto: ScheduleDto) => new Schedule(scheduleDto)))

const buildCalendarEventTitle = (timeSlot: TimeSlot, schedule: Schedule) =>
  `${timeSlot
    .registrations
    .flatMap(registration => registration.participants)
    .join(', ')} (${schedule.name})`

const buildCalendarEventDescription = (timeSlot: TimeSlot, schedule: Schedule) => {
  const url = window.location.href
  const title = schedule.name
  const players = timeSlot.registrations.length <= 1
    ? `Participants:\n${timeSlot
      .registrations
      .flatMap(registration => registration.participants)
      .map((participant, index) => `${index + 1}. ${participant}\n`)
      .join('')}`
    : timeSlot
      .registrations
      .map(registration => registration.participants)
      .map((participants, entryIndex) =>
        `Participants for entry #${entryIndex + 1}:\n${participants
          .map((participant, index) =>
            `${index + 1}. ${participant}`)
          .join('\n')}`)
      .join('\n\n')
  return `${title}\n${url}\n\n${players}`
}


const ScheduleViewer: FC<ScheduleRegistrationProps> = (props: ScheduleRegistrationProps) => {
  const [scheduleState, setScheduleState] = useState<Schedule | null | undefined>()
  const classes = useStyles()

  useEffect(() => {
    getSchedule(props.scheduleId)
      .then((schedule: Schedule) => {
        schedule.timeSlots.sort(TimeSlot.compareFn)
        setScheduleState(schedule)
      })
      .catch((err: Response) => {
        if (err.status === StatusCodes.NOT_FOUND) {
          setScheduleState(null)
        } else {
          console.error(err)
        }
      })
  }, [props.scheduleId])

  return <Container>
    {!scheduleState
      ? scheduleState === null && <div>Sorry. `<code>{props.scheduleId}</code>` is not a valid scheduleState id.</div>
      : <div style={{ textAlign: 'left', width: 'fit-content', margin: 'auto' }}>
        <label>Schedule for: {scheduleState.name}</label>
        <span style={{ display: 'block' }}>All dates and times are given in your local timezone.</span>
        {!scheduleState.active && <div><br />This scheduleState is currently inactive and registration is closed.</div>}
        {scheduleState
          .timeSlots
          .filter(timeSlot => timeSlot.registrations.length > 0)
          .map(timeSlot =>
            <List
              key={`timeslot-${timeSlot.id}`}
              className={classes.root}
              subheader={
                <ListItemText
                  className={classes.rootHeader}
                  primary={<>
                    {moment(timeSlot.dateTime).format(`ddd ${new DateFnsUtils().dateTime24hFormat}`)}
                    <div className={classes.addToCalendar}>
                      <AddToCalendar
                        event={{
                          title: buildCalendarEventTitle(timeSlot, scheduleState),
                          description: buildCalendarEventDescription(timeSlot, scheduleState),
                          location: '',
                          startTime: timeSlot.dateTime,
                          endTime: moment(timeSlot.dateTime).add(1, 'h').toDate(),
                        }}
                        buttonLabel='Add to calendar'
                      />
                    </div>
                  </>}
                  secondary={
                    `(${timeSlot.registrations.length} / ${timeSlot.maximumEntries}` +
                    ` entr${timeSlot.registrations.length === 1 ? 'y' : 'ies'})`
                  }
                />
              }
            >
              {timeSlot.participantsPerEntry <= 1 &&
                <ListItemText secondary='Participants' className={classes.nested} />
              }
              <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                {timeSlot.registrations.map((registration, registrationIndex) =>
                  <List
                    key={`registration-${registration.id}`}
                    component='div'
                    disablePadding
                    subheader={
                      timeSlot.participantsPerEntry > 1
                        ? <ListItemText secondary='Participants' />
                        : undefined
                    }
                    className={classes.nested}
                  >
                    {registration.participants.map((participant, participantIndex) =>
                      <ListItem key={`participant-${participantIndex}`} className={classes.item}>
                        <ListItemText
                          primary={
                            `${(timeSlot.participantsPerEntry > 1
                              ? participantIndex
                              : registrationIndex) + 1
                            }. ${participant}`
                          }
                        />
                      </ListItem>)}
                  </List>)}
              </div>
            </List>)}
      </div>
    }

  </Container>
}

export default ScheduleViewer
