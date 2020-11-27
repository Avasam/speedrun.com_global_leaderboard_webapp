import { Alert, OverlayTrigger, ProgressBar, Tooltip } from 'react-bootstrap'
import React, { useEffect, useState } from 'react'
import { AlertProps } from 'react-bootstrap/Alert'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faInfoCircle } from '@fortawesome/free-solid-svg-icons'

type UpdateMessageProps = {
  variant: AlertProps['variant']
  message: JSX.Element | string
  updateStartTime: number | null | undefined
}

const progressBarTickInterval = 16 // 60 FPS
const minutes5 = 5_000 * 60
let progressTimer: NodeJS.Timeout
let position: number

const renderRow = (rows: any[]) => {
  return rows.map((row, rowi) =>
    <tr key={`row${rowi}`}>
      <td>
        {Math.round((position += row.levelFraction) * 10) / 10}
      </td>
      <td>
        {row.gameName} - {row.categoryName}{row.levelName ? ` (${row.levelName})` : ''}
      </td>
      <td>
        {(row.points as number).toFixed(2)}
      </td>
    </tr>
  )
}

export const renderScoreTable = (baseString: string) => {
  position = 0
  const allElements = baseString
    .split('\n')
    .map(row =>
      row.split('|')
        .map(rowItem =>
          rowItem.trim()))
  const firstTableElement = allElements.findIndex(element => element.length === 2)
  const topMessage = allElements
    .slice(0, firstTableElement)
    .reduce((prev, curr) => prev + `${curr[0]}\n`, '')
    .trim()

  // Note: TableElements is used for rendering old string formatted table
  const tableElements = allElements.slice(firstTableElement)

  let topRuns: any[] = []
  let lesserRuns: any[] = []

  if (tableElements.length === 1 && tableElements[0].length === 1) {
    try {
      const scoreDetails = JSON.parse(tableElements[0][0])
      topRuns = scoreDetails[0]
      lesserRuns = scoreDetails[1]
    } catch {
      // suppress
    }
  }

  return <>
    <div>{topMessage}</div>
    {topRuns.length > 0 && <label>Top 100 runs:</label>}
    <table className="scoreDetailsTable">
      <thead>
        <tr>
          <th>#{topRuns.length > 0 && <OverlayTrigger
            placement="bottom"
            overlay={
              <Tooltip
                id="levelFractionInfo"
              >Individual Levels (IL) are weighted and scored to a fraction of a Full Game run. See the About page for a complete explanation.</Tooltip>
            }
          >
            <FontAwesomeIcon icon={faInfoCircle} />
          </OverlayTrigger>}</th>
          <th>Game - Category (Level)</th>
          <th>Points</th>
        </tr>
      </thead>
      {topRuns.length > 0
        ? <tbody>
          {renderRow(topRuns)}
        </tbody>
        : <tbody>
          {/* Note: TableElements is used for rendering old string formatted table */}
          {tableElements.slice(2).map((row, rowi) =>
            <tr key={`row${rowi}`}>
              <td>{rowi + 1}</td>
              {row.map((element, elementi) =>
                <td key={`element${elementi}`}>
                  {element}
                </td>
              )}
            </tr>
          )}
        </tbody>
      }
    </table >
    {lesserRuns.length > 0 && <>
      <br />
      <label>Other runs:</label>
      <table className="scoreDetailsTable">
        <thead>
          <tr>
            <th>#</th>
            <th>Game - Category (Level)</th>
            <th>Points</th>
          </tr>
        </thead>
        <tbody>
          {renderRow(lesserRuns)}
        </tbody>
      </table>
    </>}
  </>
}

const UpdateMessage = (props: UpdateMessageProps) => {
  const [currentTime, setCurrentTime] = useState<number>(new Date().getTime())

  useEffect(() => {
    if (props.updateStartTime) {
      setCurrentTime(new Date().getTime())
      progressTimer = setInterval(
        () => setCurrentTime(new Date().getTime()),
        progressBarTickInterval,
      )
    } else {
      clearInterval(progressTimer)
    }

    // Clear timer to prevent leaks
    return () => clearInterval(progressTimer)

    // Note: I don't actually care about players dependency and don't want to rerun this code on players change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.updateStartTime])

  return <Alert
    variant={props.variant}
    style={{ visibility: props.message ? 'visible' : 'hidden' }}
  >
    {props.message || '&nbsp;'}
    {props.updateStartTime != null &&
      <ProgressBar
        animated
        variant="info"
        now={(1 - (currentTime - props.updateStartTime) / minutes5) * 100}
      />}
  </Alert>
}

export default UpdateMessage
