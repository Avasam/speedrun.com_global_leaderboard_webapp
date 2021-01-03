import { Button, Card, CardActions, CardContent, Container, FormControl, FormGroup, FormLabel, InputLabel, Link, MenuItem, Select, TextField } from '@material-ui/core'
import { FC, useEffect, useRef, useState } from 'react'
import { Schedule, ScheduleDto } from '../models/Schedule'
import { apiGet, apiPost } from '../fetchers/Api'
import DateFnsUtils from '@date-io/moment'
import { SelectInputProps } from '@material-ui/core/Select/SelectInput'
import { TimeSlot } from '../models/TimeSlot'
import moment from 'moment'

interface ScheduleRegistrationProps {
  registrationLink: string
}

const entriesLeft = (timeSlot: TimeSlot) => timeSlot.maximumEntries - timeSlot.registrations.length

const timeSlotLabelPaddingRight = 40

const getSchedule = (id: number, registrationKey: string) =>
  apiGet(`schedules/${id}`, { registrationKey })
    .then(res => res.json().then((scheduleDto: ScheduleDto) => new Schedule(scheduleDto)))

const postRegistration = (timeSlotId: number, participants: string[], registrationKey: string) =>
  apiPost(`time-slots/${timeSlotId}/registrations`, { participants, registrationKey })
    .then(res => res.json())

const ScheduleRegistration: FC<ScheduleRegistrationProps> = (props: ScheduleRegistrationProps) => {
  const [scheduleState, setScheduleState] = useState<Schedule | null | undefined>()
  const [registrationKeyState, setRegistrationKeyState] = useState<string>('')
  const [selectedTimeSlot, setSelectedTimeSlot] = useState<TimeSlot | undefined>()
  const [timeSlotLabelWidth, setTimeSlotLabelWidth] = useState(0)
  const [participants, setParticipants] = useState<string[]>([])
  const [formValidity, setFormValidity] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const timeSlotInputLabel = useRef<HTMLLabelElement>(null)

  const checkFormValidity = () => {
    const participantCount = selectedTimeSlot?.participantsPerEntry
    const actualParticipants = participants.slice(0, participantCount)
    const valid = actualParticipants.length === participantCount && actualParticipants.every(participant => !!participant)
    setFormValidity(valid)
  }

  useEffect(checkFormValidity, [selectedTimeSlot, participants])

  useEffect(() => {
    const splitIndex = props.registrationLink.indexOf('-')
    const id = Number.parseInt(props.registrationLink.slice(0, Math.max(0, splitIndex)))
    const registrationKey = props.registrationLink.slice(splitIndex + 1)
    setRegistrationKeyState(registrationKey)
    getSchedule(id, registrationKey)
      .then((schedule: Schedule) => {
        schedule.timeSlots.sort(TimeSlot.compareFn)
        setScheduleState(schedule)
        setTimeSlotLabelWidth((timeSlotInputLabel.current?.offsetWidth || 0) - timeSlotLabelPaddingRight)
      })
      .catch(err => {
        if (err.status === 404) {
          setScheduleState(null)
        } else {
          console.error(err)
        }
      })
  }, [props.registrationLink])

  const selectTimeSlot: SelectInputProps['onChange'] = event => {
    setSelectedTimeSlot(scheduleState?.timeSlots.find(timeSlot => timeSlot.id === Number.parseInt(event.target.value as string)))
    setErrorMessage('')
  }

  const handleParticipantChange = (index: number, name: string) => {
    participants[index] = name
    setParticipants([...participants])
  }

  const sendRegistrationForm = () => {
    if (!selectedTimeSlot) return
    postRegistration(selectedTimeSlot.id, participants.slice(0, selectedTimeSlot.participantsPerEntry), registrationKeyState)
      .then(() => {
        localStorage.removeItem('register')
        window.location.href = `${window.location.pathname}?view=${scheduleState?.id}`
      })
      .catch(err => {
        if (err.status === 507) {
          if (!scheduleState) { return }
          const index = scheduleState.timeSlots.findIndex(timeSlot => timeSlot.id === selectedTimeSlot.id)
          scheduleState.timeSlots[index].maximumEntries = 0
          setScheduleState({
            ...scheduleState,
            registrationLink: scheduleState.registrationLink,
          })
          setSelectedTimeSlot(scheduleState.timeSlots[index])
          err.json().then((response: { message: string, authenticated: boolean }) => setErrorMessage(response.message))
        } else {
          console.error(err)
        }
      })
  }

  return <Container>
    {!scheduleState
      ? scheduleState === null && <div>Sorry. `<code>{props.registrationLink}</code>` does not lead to an existing registration form.</div>
      : <Card>
        <CardContent style={{ textAlign: 'left' }}>
          <label>Schedule for: {scheduleState.name}</label>
          <Link href={`${window.location.href}?view=${scheduleState.id}`} target='blank' style={{ display: 'block' }}>
            Click here to view the current registrations in a new tab
          </Link>
          <span style={{ display: 'block' }}>All dates and times are given in your local timezone.</span>
          {!scheduleState.active
            ? <div><br />Sorry. This schedule is currently inactive and registration is closed.</div>
            : <FormGroup>
              <FormControl variant='outlined' style={{ margin: '16px 0' }}>
                <InputLabel
                  ref={timeSlotInputLabel}
                  id='time-slot-select-label'
                  style={{ paddingRight: `${timeSlotLabelPaddingRight}px` }}
                >
                  Choose your time slot amongst the following
                </InputLabel>
                <Select
                  labelId='time-slot-select-label'
                  id='time-slot-select'
                  value={selectedTimeSlot?.id || ''}
                  onChange={selectTimeSlot}
                  labelWidth={timeSlotLabelWidth}
                >
                  {scheduleState.timeSlots.map(timeSlot =>
                    <MenuItem
                      key={`timeslot-${timeSlot.id}`}
                      value={timeSlot.id}
                      disabled={entriesLeft(timeSlot) <= 0 || timeSlot.dateTime <= new Date()}
                    >{
                        `${moment(timeSlot.dateTime).format(`ddd ${new DateFnsUtils().dateTime24hFormat}`)
                        } (${timeSlot.dateTime <= new Date()
                          ? 'past deadline'
                          : entriesLeft(timeSlot) <= 0
                            ? 'full'
                            : `${entriesLeft(timeSlot)} / ${timeSlot.maximumEntries}` +
                            ` entr${entriesLeft(timeSlot) === 1 ? 'y' : 'ies'} left`
                        })`
                      }</MenuItem>)}
                </Select>
              </FormControl>
              {selectedTimeSlot && entriesLeft(selectedTimeSlot) > 0 &&
                <>
                  <FormLabel>
                    Please write down your name
                    {selectedTimeSlot.participantsPerEntry > 1 &&
                      ' as well as all other participants playing with or against you in the same match'}
                  </FormLabel>
                  {new Array(...new Array(selectedTimeSlot.participantsPerEntry)).map((_, index) =>
                    <TextField
                      key={`participant-${index}`}
                      label={`Participant${selectedTimeSlot.participantsPerEntry > 1 ? ` ${index + 1}` : ''}'s name`}
                      onChange={event => handleParticipantChange(index, event.target.value)}
                    />)}
                </>}
            </FormGroup>
          }
        </CardContent>
        <CardActions>
          <Button
            size='small'
            variant='contained'
            color='primary'
            disabled={
              !formValidity ||
              !selectedTimeSlot ||
              entriesLeft(selectedTimeSlot) <= 0
            }
            onClick={() =>
              formValidity &&
              selectedTimeSlot &&
              entriesLeft(selectedTimeSlot) > 0 &&
              sendRegistrationForm()
            }
          >
            Sign {selectedTimeSlot?.participantsPerEntry === 1 ? 'me' : 'us'} up!
          </Button>
          <span style={{ color: 'red' }}>{errorMessage}</span>
        </CardActions>
      </Card>
    }

  </Container>
}

export default ScheduleRegistration
